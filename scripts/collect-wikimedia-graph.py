#!/usr/bin/env python3
"""Wikidata → Wikimedia Commons SVG 후보 수집기.

기존 ``wiki-fetch.py``가 이미 알고 있는 파일명만 내려받는 도구라면,
이 도구는 브랜드명에서 Wikidata의 로고(P154)를 찾고 Commons의 관련 SVG를
후보로 모은다. 운영 DB를 바꾸지 않으며, ``--download``를 명시했을 때만
검수용 staging 폴더에 SVG와 manifest를 저장한다.

예시:
  python3 scripts/collect-wikimedia-graph.py --input _clients/collect-wanted.json --limit 8
  python3 scripts/collect-wikimedia-graph.py --input _clients/collect-wanted.json --limit 8 \
    --download --out /private/tmp/semologo-wikimedia-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from assetguard import check, safe_write  # noqa: E402

UA = "VibersLogoDB/1.1 (contact: vibers.leo@gmail.com)"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def api_get(base: str, params: dict) -> dict:
    url = base + "?" + urllib.parse.urlencode({**params, "format": "json"})
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read())


def normalise(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[^0-9a-z가-힣]", "", value)


def safe_slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "brand"


def input_brands(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    brands = raw.get("brands", raw if isinstance(raw, list) else [])
    if not isinstance(brands, list):
        raise ValueError("brands 배열이 없는 JSON입니다")
    return [brand for brand in brands if brand.get("name_ko") or brand.get("name_en")]


def search_entity(brand: dict) -> dict | None:
    """동일 명칭/별칭이 있는 경우만 수용해 동명이인 자동 수집을 막는다."""
    names = [brand.get("name_ko", ""), brand.get("name_en", "")]
    wanted = {normalise(name) for name in names if normalise(name)}
    for language, query in (("ko", brand.get("name_ko")), ("en", brand.get("name_en"))):
        if not query:
            continue
        data = api_get(WIKIDATA_API, {
            "action": "wbsearchentities", "search": query, "language": language,
            "limit": 6, "uselang": language,
        })
        for hit in data.get("search", []):
            labels = [hit.get("label", ""), *(hit.get("aliases") or [])]
            if wanted.intersection(normalise(label) for label in labels):
                return {"id": hit["id"], "label": hit.get("label", ""), "description": hit.get("description", "")}
    return None


def entity_logo_filename(qid: str) -> str | None:
    data = api_get(WIKIDATA_API, {"action": "wbgetentities", "ids": qid, "props": "claims"})
    claims = data.get("entities", {}).get(qid, {}).get("claims", {}).get("P154", [])
    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str) and value.lower().endswith(".svg"):
            return value
    return None


def commons_search(brand: dict) -> list[str]:
    """P154 외에 검색으로 얻은 결과는 변형 후보일 뿐 자동 채택하지 않는다."""
    queries = [brand.get("name_en", ""), brand.get("name_ko", "")]
    found: list[str] = []
    for query in dict.fromkeys(value for value in queries if value):
        try:
            data = api_get(COMMONS_API, {
                "action": "query", "list": "search", "srnamespace": 6,
                "srlimit": 12, "srsearch": f'filetype:svg "{query}"',
            })
        except OSError as error:
            print(f"  Commons 검색 건너뜀 ({query}): {error}", file=sys.stderr)
            continue
        for hit in data.get("query", {}).get("search", []):
            title = hit.get("title", "")
            if title.lower().endswith(".svg"):
                found.append(title.removeprefix("File:"))
    return list(dict.fromkeys(found))


def commons_file(filename: str) -> dict | None:
    data = api_get(COMMONS_API, {
        "action": "query", "titles": f"File:{filename}", "prop": "imageinfo",
        "iiprop": "url|mime|mediatype|size|extmetadata",
    })
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    info = next(iter(page.get("imageinfo", [])), None)
    if not info or info.get("mime") != "image/svg+xml":
        return None
    metadata = info.get("extmetadata", {})
    return {
        "filename": filename,
        "original_url": info.get("url"),
        "bytes": info.get("size"),
        "license": metadata.get("LicenseShortName", {}).get("value", ""),
        "artist": metadata.get("Artist", {}).get("value", ""),
    }


def download(candidate: dict, output: Path, max_bytes: int) -> tuple[bool, str]:
    url = candidate.get("original_url")
    if not url:
        return False, "원본 URL 없음"
    if candidate.get("bytes", 0) > max_bytes:
        return False, f"파일이 너무 큼 ({candidate['bytes']:,}B > {max_bytes:,}B)"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        encoding = "utf-16-le" if raw[:2] == b"\xff\xfe" else "utf-16-be"
        raw = raw.decode(encoding).encode("utf-8")
    ok, reason = check(output, raw)
    if not ok:
        return False, reason
    if b"data:image/" in raw.lower() or re.search(rb"<image\b", raw, re.I):
        return False, "래스터 내장 SVG"
    if not safe_write(output, raw, quiet=True):
        return False, "assetguard 저장 거부"
    candidate["sha256"] = hashlib.sha256(raw).hexdigest()
    candidate["downloaded_bytes"] = len(raw)
    return True, reason


def collect(brand: dict, download_enabled: bool, output: Path | None, max_bytes: int) -> dict:
    entity = search_entity(brand)
    result = {
        "brand": {key: brand.get(key, "") for key in ("id", "name_ko", "name_en", "domain", "category")},
        "status": "no_exact_wikidata_match", "entity": entity, "primary": None, "variants": [],
    }
    if not entity:
        return result
    primary_name = entity_logo_filename(entity["id"])
    filenames = []
    if primary_name:
        filenames.append((primary_name, "wikidata_p154"))
    filenames.extend((name, "commons_search") for name in commons_search(brand) if name != primary_name)
    for filename, provenance in filenames:
        item = commons_file(filename)
        if not item:
            continue
        item["provenance"] = provenance
        if download_enabled and output:
            prefix = safe_slug(brand.get("id") or brand.get("name_en") or brand.get("name_ko"))
            suffix = "primary" if provenance == "wikidata_p154" else f"variant-{len(result['variants']) + 1}"
            ok, reason = download(item, output / prefix / f"{suffix}.svg", max_bytes)
            item["download_status"] = "saved" if ok else f"rejected: {reason}"
        if provenance == "wikidata_p154":
            result["primary"] = item
        else:
            result["variants"].append(item)
    result["status"] = "candidate_found" if result["primary"] or result["variants"] else "no_svg_candidate"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Wikidata→Commons SVG 후보 수집 (운영 DB 미변경)")
    parser.add_argument("--input", type=Path, required=True, help="brands 배열이 든 JSON")
    parser.add_argument("--limit", type=int, default=10, help="처리할 최대 브랜드 수")
    parser.add_argument("--offset", type=int, default=0, help="입력 목록에서 건너뛸 브랜드 수")
    parser.add_argument("--download", action="store_true", help="후보 SVG를 staging 폴더에 저장")
    parser.add_argument("--out", type=Path, help="manifest와 후보 SVG를 저장할 staging 폴더")
    parser.add_argument("--delay", type=float, default=0.4, help="브랜드 간 API 대기 시간(초)")
    parser.add_argument("--max-bytes", type=int, default=2_000_000, help="다운로드 허용 SVG 최대 크기")
    args = parser.parse_args()
    if args.download and not args.out:
        parser.error("--download에는 --out이 필요합니다")
    if args.limit < 1 or args.offset < 0:
        parser.error("--limit은 1 이상, --offset은 0 이상이어야 합니다")

    brands = input_brands(args.input)[args.offset:args.offset + args.limit]
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    results = []
    for index, brand in enumerate(brands, 1):
        label = brand.get("name_ko") or brand.get("name_en")
        print(f"[{index}/{len(brands)}] {label}")
        try:
            result = collect(brand, args.download, args.out, args.max_bytes)
        except Exception as error:  # 한 브랜드 실패가 배치를 멈추지 않게 한다.
            result = {"brand": brand, "status": "error", "error": str(error), "primary": None, "variants": []}
        results.append(result)
        primary = "P154" if result.get("primary") else "-"
        print(f"  {result['status']} | {primary} | 변형 {len(result.get('variants', []))}")
        if index < len(brands):
            time.sleep(args.delay)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "staging" if args.download else "discovery_only",
        "input": str(args.input), "count": len(results), "results": results,
    }
    encoded = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.out:
        (args.out / "manifest.json").write_text(encoded + "\n")
        print(f"\nmanifest: {args.out / 'manifest.json'}")
    else:
        print(encoded)
    found = sum(result["status"] == "candidate_found" for result in results)
    saved = sum(1 for result in results for item in [result.get("primary"), *result.get("variants", [])] if item and item.get("download_status") == "saved")
    print(f"완료: 후보 브랜드 {found}/{len(results)}, 저장 SVG {saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
