#!/usr/bin/env python3
"""Logos Apps의 대량 SVG 목록을 세모로고 수집 대기열로 동기화한다.

이 스크립트는 절대로 SVG를 다운로드하거나 brands.json을 바꾸지 않는다. 원본
저장소는 코드와 사이트에 MIT를 적용하지만 로고 상표의 사용 권한은 부여하지
않으므로, 여기서는 미보유 후보와 원본 경로만 기록하고 개별 검토를 거친다.

사용:
  python3 scripts/discover-logos-apps.py
  python3 scripts/discover-logos-apps.py --limit 100
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
OUT = CLIENTS / "logos-apps-discovery.json"
TREE_API = "https://api.github.com/repos/ln-dev7/logos-apps/git/trees/master?recursive=1"
SOURCE_URL = "https://github.com/ln-dev7/logos-apps"
UA = "VibersLogoDiscovery/1.0 (https://semologo.com)"


def slug(value: str) -> str:
    value = value.lower().replace("_", "-")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return re.sub(r"-{2,}", "-", value)


def source_items(tree: list[dict]) -> list[dict]:
    """브랜드별 대표 후보를 하나만 남긴다. 심볼을 워드마크보다 우선한다."""
    by_id: dict[str, dict] = {}
    for item in tree:
        path = item.get("path", "")
        if item.get("type") != "blob" or not path.startswith("logos/") or not path.endswith(".svg"):
            continue
        filename = Path(path).stem
        form = "wordmark" if filename.endswith("-wordmark") else "symbol"
        brand_id = slug(filename.removesuffix("-wordmark"))
        if not brand_id:
            continue
        candidate = {"id": brand_id, "path": path, "form": form}
        existing = by_id.get(brand_id)
        if not existing or (existing["form"] == "wordmark" and form == "symbol"):
            by_id[brand_id] = candidate
    return sorted(by_id.values(), key=lambda item: item["id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="대기열 출력 수 제한 (0=전체)")
    args = parser.parse_args()

    data = json.loads(BRANDS.read_text())
    brands = data.get("brands", data)
    known = {slug(brand.get("id", "")) for brand in brands}
    # 별칭·영문명이 slug와 일치하는 경우도 보유로 본다. 동일 브랜드를 다른 표기로
    # 다시 제안하지 않기 위한 보수적 가드다.
    for brand in brands:
        for name in [brand.get("name_en", ""), *(brand.get("aliases") or [])]:
            value = slug(name)
            if value:
                known.add(value)

    request = urllib.request.Request(TREE_API, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=45) as response:
        remote = json.loads(response.read())
    if remote.get("truncated"):
        raise RuntimeError("GitHub tree 응답이 잘렸다. 대량 수집을 중단한다.")

    candidates = [item for item in source_items(remote.get("tree", [])) if item["id"] not in known]
    if args.limit:
        candidates = candidates[:args.limit]
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"name": "Logos Apps", "url": SOURCE_URL, "tree_sha": remote.get("sha", "")},
        "policy": "발굴 전용. 상표·정확성·출처를 검토하기 전에는 다운로드·서비스 반영 금지.",
        "known_brand_count": len(brands),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=1) + "\n")
    print(f"Logos Apps: SVG 브랜드 {len(source_items(remote.get('tree', []))):,} / 미보유 후보 {len(candidates):,}")
    print(f"대기열: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
