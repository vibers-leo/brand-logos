#!/usr/bin/env python3
"""검토를 통과한 theSVG 형태만 기존 브랜드에 추가한다.

대량 발굴(`discover-thesvg.py`)과 반대되는 도구다. 이 스크립트는 명시한
브랜드·theSVG 슬러그만 반입하며, brands.json의 대표 logo.svg를 교체하지
않는다. 원본은 `sources/thesvg/`에 보존하고 variants 매니페스트가 형태별
다운로드 선택지를 만든다.

예:
  python3 scripts/import-thesvg-forms.py --brand macos --source-id macos
  python3 scripts/import-thesvg-forms.py --brand vercel --source-id vercel
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENTS = ROOT / "_clients"
BRANDS = CLIENTS / "brands.json"
REGISTRY_URL = "https://thesvg.org/api/registry.json"
SVG_URL = "https://thesvg.org/icons/{slug}/{variant}.svg"
UA = "VibersLogoCollector/1.0 (https://semologo.com)"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import safesvg  # noqa: E402


def filename(slug: str, variant: str) -> str:
    # build-logo-variants.py가 파일명으로 형태를 확정할 수 있게 한다.
    normalized = url_variant(variant)
    if normalized.startswith("wordmark"):
        suffix = normalized[len("wordmark"):]
        return f"{slug}-wordmark{suffix}.svg"
    # default/color/mono는 '대표 색상'일 뿐 형태를 뜻하지 않는다. 파일명으로
    # 심볼을 강제하면 macOS처럼 가로 워드마크를 심볼로 오분류하게 된다.
    return f"{slug}-{normalized}.svg"


def url_variant(variant: str) -> str:
    """레지스트리 camelCase 키를 CDN의 kebab-case 경로로 바꾼다."""
    return re.sub(r"(?<!^)([A-Z])", r"-\1", variant).lower()


def get_registry() -> list[dict]:
    req = urllib.request.Request(REGISTRY_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read())
    icons = data.get("icons", [])
    if not isinstance(icons, list):
        raise RuntimeError("theSVG 레지스트리 형식이 예상과 다릅니다.")
    return icons


def fetch_svg(slug: str, variant: str) -> bytes:
    url = SVG_URL.format(slug=slug, variant=url_variant(variant))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/svg+xml"})
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read()
    if b"<svg" not in raw[:4096].lower() or b"<html" in raw[:512].lower():
        raise RuntimeError(f"{variant}: SVG가 아닌 응답")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", required=True, help="세모로고 기존 브랜드 ID")
    parser.add_argument("--source-id", required=True, help="theSVG registry slug")
    parser.add_argument("--variants", help="쉼표로 제한 (기본: source가 제공하는 전체 형태)")
    parser.add_argument("--remove", action="store_true", help="이 브랜드의 기존 theSVG 반입본을 제거")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = json.loads(BRANDS.read_text())
    brand = next((item for item in data.get("brands", []) if item.get("id") == args.brand), None)
    if not brand:
        raise SystemExit(f"브랜드 없음: {args.brand}")
    source = next((item for item in get_registry() if item.get("slug") == args.source_id), None)
    if not source:
        raise SystemExit(f"theSVG slug 없음: {args.source_id}")
    if args.remove:
        target = CLIENTS / args.brand / "sources" / "thesvg"
        for path in target.glob("*") if target.exists() else []:
            path.unlink()
        if target.exists():
            target.rmdir()
        prefix = f"thesvg:{args.source_id}"
        brand["sources"] = [entry for entry in (brand.get("sources") or [])
                            if entry.get("provider") != prefix]
        BRANDS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        print(f"✅ {args.brand}의 theSVG:{args.source_id} 반입본 제거")
        return 0
    available = [value for value in (source.get("variants") or []) if isinstance(value, str)]
    wanted = [value.strip() for value in args.variants.split(",")] if args.variants else available
    missing = sorted(set(wanted) - set(available))
    if missing:
        raise SystemExit(f"theSVG가 제공하지 않는 형태: {', '.join(missing)}")
    if not wanted:
        raise SystemExit("반입할 형태가 없습니다.")
    print(f"{args.brand} ← theSVG:{args.source_id} ({', '.join(wanted)})")
    if args.dry_run:
        return 0

    # 모두 받아 검증한 다음에만 디스크를 바꾼다. 일부만 반입되는 상태를 막는다.
    payloads = {variant: fetch_svg(args.source_id, variant) for variant in wanted}
    target = CLIENTS / args.brand / "sources" / "thesvg"
    target.mkdir(parents=True, exist_ok=True)
    entries = brand.setdefault("sources", [])
    # 초기 반입기의 전체 카탈로그 기준 경로(`macos/sources/...`)가 남아 있으면
    # 브랜드 폴더 기준으로 바로잡는다. 매니페스트 생성기는 이 규약만 읽는다.
    old_prefix = f"{args.brand}/"
    for entry in entries:
        value = entry.get("file")
        if isinstance(value, str) and value.startswith(old_prefix):
            entry["file"] = value[len(old_prefix):]
    for variant, raw in payloads.items():
        svg_name = filename(args.source_id, variant)
        svg_path = target / svg_name
        svg_path.write_bytes(raw)
        # SVG별 PNG도 함께 둔다. 변형 카드의 PNG 다운로드가 404가 되지 않는다.
        safesvg.render_to_file(raw, svg_path.with_suffix(".png"), 800, transparent=True)
        # brands.json의 sources.file은 `_clients/{brand}/` 기준 경로다.
        rel = str(svg_path.relative_to(CLIENTS / args.brand))
        if not any(entry.get("file") == rel for entry in entries):
            entries.append({
                "provider": f"thesvg:{args.source_id}",
                "file": rel,
                "label": f"theSVG {variant}",
            })
    BRANDS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"✅ {len(payloads)}개 SVG·PNG 반입 완료 — 다음: build-logo-variants.py --brand {args.brand} --force")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
