#!/usr/bin/env python3
"""
brands-slim.json 생성

왜 필요한가
-----------
brands-slim.json 은 목록 그리드(semologo BrandGrid)가 읽는 경량판인데,
지금까지 **생성 스크립트 없이 임시로 만들어져** 있었다. 그래서 brands.json 에
브랜드를 추가하고 slim 을 다시 만드는 걸 잊으면 신규 브랜드가 목록에 안 뜬다
(2026-08-08 에 ibk-en 이 실제로 그렇게 누락됐다).

담는 필드
---------
목록에서 실제로 쓰는 것만 담는다. 원본 2.9MB → 약 1MB.
  id, name_ko, name_en, category, has_svg, has_png, added_at
  variants_n — 변형 개수 (변형 배지·필터용, 2 이상일 때만 넣어 용량 절약)

사용
----
  python3 scripts/build-slim.py            # 생성
  python3 scripts/build-slim.py --check    # 최신인지만 확인 (CI용, 다르면 exit 1)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"
BRANDS_JSON = BASE / "brands.json"
SLIM_JSON = BASE / "brands-slim.json"
INDEX_JSON = BASE / "variants-index.json"


def build() -> list:
    brands = json.loads(BRANDS_JSON.read_text())["brands"]

    variants_n: dict[str, int] = {}
    if INDEX_JSON.exists():
        try:
            idx = json.loads(INDEX_JSON.read_text()).get("brands", {})
            variants_n = {k: v.get("n", 0) for k, v in idx.items()}
        except Exception:
            pass

    out = []
    for b in brands:
        row = OrderedDict([
            ("id", b["id"]),
            ("name_ko", b.get("name_ko", "")),
            ("name_en", b.get("name_en", "")),
            ("category", b.get("category", "")),
            ("has_svg", bool(b.get("logo_svg") or b.get("has_svg"))),
            ("has_png", bool(b.get("logo_png") or b.get("has_png"))),
            ("added_at", b.get("added_at", "")),
        ])
        n = variants_n.get(b["id"], 0)
        if n > 1:                      # 1종뿐이면 굳이 안 담는다 (용량)
            row["variants_n"] = n
        out.append(row)
    return out


def serialize(rows: list) -> str:
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="다시 생성했을 때 현재 파일과 같은지만 확인 (CI용)")
    args = ap.parse_args()

    rows = build()
    text = serialize(rows)

    if args.check:
        current = SLIM_JSON.read_text() if SLIM_JSON.exists() else ""
        if current == text:
            print(f"✅ brands-slim.json 최신 — {len(rows):,}개")
            return 0
        print("❌ brands-slim.json 이 brands.json 과 어긋남 — "
              "`python3 scripts/build-slim.py` 로 재생성 필요")
        try:
            cur = json.loads(current)
            cur_ids = {r["id"] for r in cur}
            new_ids = {r["id"] for r in rows}
            missing = sorted(new_ids - cur_ids)[:10]
            extra = sorted(cur_ids - new_ids)[:10]
            print(f"   현재 {len(cur):,}개 vs 기대 {len(rows):,}개")
            if missing:
                print(f"   slim 에 빠진 브랜드: {missing}")
            if extra:
                print(f"   slim 에만 있는 브랜드: {extra}")
        except Exception:
            pass
        return 1

    SLIM_JSON.write_text(text)
    n_var = sum(1 for r in rows if r.get("variants_n"))
    print(f"✅ brands-slim.json — {len(rows):,}개 "
          f"({SLIM_JSON.stat().st_size:,}B, 변형 2종 이상 {n_var:,}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
