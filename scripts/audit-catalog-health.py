#!/usr/bin/env python3
"""세모로고 카탈로그의 활용 가능성을 수치로 기록한다.

수집 건수만 보면 PNG 전용·형태 미비·상세 메타 누락이 가려진다. 이 리포트는
매 수집 뒤 생성해 다음 수집 우선순위와 서비스 품질 점검에 사용한다.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENTS = ROOT / "_clients"


def queue_count(name: str) -> int:
    path = CLIENTS / name
    if not path.exists():
        return 0
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return len(data)
    return len(data.get("brands") or data.get("items") or data.get("candidates") or [])


def main() -> int:
    brands = json.loads((CLIENTS / "brands.json").read_text())["brands"]
    index_path = CLIENTS / "variants-index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"brands": {}}
    variant_rows = index.get("brands") or {}
    variants = len(variant_rows)
    multi_form = sum(1 for row in variant_rows.values() if len(set(row.get("forms") or [])) >= 2)
    provider = Counter()
    for brand in brands:
        for source in brand.get("sources") or []:
            key = (source.get("provider") or "unknown").split(":", 1)[0]
            provider[key] += 1

    svg = sum(bool(brand.get("has_svg") or brand.get("logo_svg")) for brand in brands)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog": {
            "brands": len(brands), "svg": svg, "png_only": len(brands) - svg,
            # build-brand-json 직후 실행되므로 기대 생성 수를 기록한다. 개별 파일을
            # 4만 번 stat하면 매일의 수집 시간을 불필요하게 늘린다.
            "detail_metadata_expected": len(brands), "variant_manifests": variants,
            "multiple_forms": multi_form,
        },
        "backlog": {
            "svg_needed": queue_count("svg-wanted.json"),
            "additional_forms_needed": queue_count("variant-wanted.json"),
            "png_render_failures": queue_count("png-render-failures.json"),
            "external_source_candidates": queue_count("logos-apps-discovery.json"),
        },
        "source_coverage": dict(provider.most_common()),
        "policy": "SVG·다중 형태·상세 메타 비율을 유지하고, 대기열은 검토 후에만 반영한다.",
    }
    out = CLIENTS / "catalog-health.json"
    out.write_text(json.dumps(output, ensure_ascii=False, indent=1) + "\n")
    print(f"카탈로그 건강도: 브랜드 {len(brands):,} / SVG {svg:,} / 다중 형태 {multi_form:,} / 상세 기대 {len(brands):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
