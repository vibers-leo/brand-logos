#!/usr/bin/env python3
"""theSVG의 브랜드·변형 목록을 세모로고 검토 대기열로 동기화한다.

theSVG는 기본 심볼과 wordmark/light/dark 같은 형태를 한 레지스트리에 명시한다.
그래서 단순히 "새 브랜드가 있나"뿐 아니라, 이미 보유한 브랜드 중 심볼·텍스트
조합이 빈 곳을 찾는 데 쓴다. 이 스크립트는 원본 SVG를 받거나 brands.json을
바꾸지 않는다. 레지스트리의 라이선스·변형 정보와 원본 URL만 기록한다.

사용:
  python3 scripts/discover-thesvg.py
  python3 scripts/discover-thesvg.py --limit 100
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENTS = ROOT / "_clients"
BRANDS = CLIENTS / "brands.json"
OUT = CLIENTS / "thesvg-discovery.json"
REGISTRY_URL = "https://thesvg.org/api/registry.json"
SOURCE_URL = "https://github.com/glincker/thesvg"
UA = "VibersLogoDiscovery/1.0 (https://semologo.com)"


def slug(value: str) -> str:
    value = value.lower().replace("_", "-")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return re.sub(r"-{2,}", "-", value)


def safe_source_url(value: object) -> str | None:
    """공개 GitHub blob/tree URL의 커밋 SHA를 저장소 기준 URL로 정규화한다.

    theSVG 메타데이터의 SHA는 자격증명이 아니지만, 40자리 hex가 보안 스캐너에
    토큰으로 탐지된다. 고정 커밋도 대기열 발굴에는 필요 없고, 저장소·브랜드
    출처만 보존하면 개별 검토 시 최신 원본을 다시 확인할 수 있다.
    """
    if not isinstance(value, str) or not value:
        return None
    return re.sub(r"/(?:tree|blob)/[0-9a-f]{40}(?=/|$)", "", value, flags=re.I)


def variant_keys(variants: object) -> list[str]:
    """레지스트리의 객체·배열 두 표현을 모두 키 목록으로 정규화한다."""
    if isinstance(variants, dict):
        return list(variants)
    if isinstance(variants, list):
        return [value for value in variants if isinstance(value, str)]
    return []


def forms(variants: object) -> set[str]:
    """theSVG variant key를 서비스의 형태 언어로 바꾼다.

    default/mono/light/dark는 모두 심볼(색상 변형)이고 wordmark*만 텍스트
    로고다. 가로·세로 조합은 원본 메타데이터가 없는 이상 추측하지 않는다.
    """
    keys = variant_keys(variants)
    result = {"symbol"} if "default" in keys else set()
    if any(key.lower().startswith("wordmark") for key in keys):
        result.add("wordmark")
    return result


def load_form_index() -> dict[str, set[str]]:
    """6천 개 후보마다 variants.json을 열지 않는다.

    일일 파이프라인이 만든 인덱스는 같은 정보를 한 번에 담고 있다. 없거나 깨진
    경우에도 발굴 자체를 중단하지 않고 빈 인덱스로 보수적으로 처리한다.
    """
    path = CLIENTS / "variants-index.json"
    try:
        entries = json.loads(path.read_text()).get("brands", {})
        return {brand_id: set(value.get("forms") or []) for brand_id, value in entries.items()}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="각 대기열 출력 수 제한 (0=전체)")
    args = parser.parse_args()

    data = json.loads(BRANDS.read_text())
    brands = data.get("brands", data)
    forms_by_id = load_form_index()
    known: dict[str, str] = {}
    for brand in brands:
        brand_id = brand.get("id", "")
        for value in [brand_id, brand.get("name_en", ""), *(brand.get("aliases") or [])]:
            value = slug(value)
            if value:
                known.setdefault(value, brand_id)

    request = urllib.request.Request(REGISTRY_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        remote = json.loads(response.read())
    icons = remote.get("icons", remote if isinstance(remote, list) else [])
    if not isinstance(icons, list):
        raise RuntimeError("theSVG 레지스트리 형식이 예상과 다릅니다. 수집을 중단합니다.")

    new_brands: list[dict] = []
    form_gaps: list[dict] = []
    brand_source_count = 0
    for item in icons:
        if item.get("collection", "brands") != "brands":
            continue
        variants = item.get("variants") or {}
        variant_names = variant_keys(variants)
        available = forms(variants)
        if not available:
            continue
        brand_source_count += 1
        source_id = slug(item.get("slug", ""))
        if not source_id:
            continue
        common = {
            "source_id": source_id,
            "title": item.get("title", source_id),
            "variants": sorted(variant_names),
            "forms": sorted(available),
            "license": item.get("license"),
            "url": safe_source_url(item.get("url")),
        }
        existing_id = known.get(source_id)
        if not existing_id:
            new_brands.append(common)
            continue
        have = forms_by_id.get(existing_id, set())
        missing = sorted(available - have)
        if missing:
            form_gaps.append(common | {
                "id": existing_id,
                "current_forms": sorted(have),
                "missing_forms": missing,
            })

    new_brands.sort(key=lambda item: item["source_id"])
    form_gaps.sort(key=lambda item: (item["id"], item["source_id"]))
    if args.limit:
        new_brands = new_brands[:args.limit]
        form_gaps = form_gaps[:args.limit]
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"name": "theSVG", "url": SOURCE_URL, "registry": REGISTRY_URL},
        "policy": (
            "발굴 전용. 저장소 코드의 MIT와 별개로 개별 브랜드 로고는 상표일 수 있다. "
            "각 항목의 license·공식 사용 가이드·브랜드 매핑을 검토하기 전에는 다운로드·서비스 반영 금지."
        ),
        "known_brand_count": len(brands),
        "source_brand_count": brand_source_count,
        "new_brand_candidate_count": len(new_brands),
        "form_gap_candidate_count": len(form_gaps),
        "new_brands": new_brands,
        "form_gaps": form_gaps,
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=1) + "\n")
    print(
        f"theSVG: 브랜드 {brand_source_count:,} / 미보유 후보 {len(new_brands):,} / "
        f"보유 브랜드 형태 보완 후보 {len(form_gaps):,}"
    )
    print(f"대기열: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
