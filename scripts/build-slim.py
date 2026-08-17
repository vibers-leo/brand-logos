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

    # 흰색 로고는 밝은 카드 배경에서 안 보인다 → 목록이 '빈 카드'처럼 보인다.
    # 매니페스트의 대표 변형 색상이 mono-light 인 브랜드를 표시해두면
    # 그리드가 그 카드만 어두운 배경으로 그릴 수 있다.
    # 판정 기준은 채도가 아니라 **밝기**다. 채도로 보면 컬러 요소가 섞인
    # 로고가 'color' 로 나와서 흰 글자가 안 보이는 걸 놓친다.
    # brands.json 의 light_logo 는 SVG 를 실제 렌더해 잉크의 40% 이상이
    # 아주 밝은지(luma>235) 재서 붙인 값이다 (scripts 로 재계산 가능).
    light: set[str] = {b["id"] for b in brands if b.get("light_logo")}

    out = []
    # seq = brands.json 에서의 위치 = 추가 순서.
    # added_at 이 날짜 단위라 같은 날 추가분끼리 순서가 없는데, 배열 위치를
    # 그때그때 계산하면 **이미 정렬된 목록을 다시 정렬할 때 순서가 뒤집힌다**
    # (2026-08-17: 서버가 정렬한 60개를 클라이언트가 재정렬해 역순이 됐다).
    # 데이터에 실어 보내면 몇 번을 정렬해도 결과가 같다.
    for i, b in enumerate(brands):
        row = OrderedDict([
            ("id", b["id"]),
            ("seq", i),
            ("name_ko", b.get("name_ko", "")),
            ("name_en", b.get("name_en", "")),
            ("category", b.get("category", "")),
            ("has_svg", bool(b.get("logo_svg") or b.get("has_svg"))),
            ("has_png", bool(b.get("logo_png") or b.get("has_png"))),
            ("added_at", b.get("added_at", "")),
        ])
        # variant_of 는 부모로 흡수된 중복 항목이다. 그리드에서 빼기 위해
        # slim 에도 실어 보낸다 (페이지는 살아 있으므로 404 는 나지 않는다).
        if b.get("variant_of"):
            row["variant_of"] = b["variant_of"]

        # 검색 전용 별칭. LG·SK 처럼 로마자가 정식 이름인 브랜드를 '엘지'로
        # 찾을 수 있게 한다. 있는 것만 담아 용량을 아낀다.
        if b.get("aliases"):
            row["aliases"] = b["aliases"]

        n = variants_n.get(b["id"], 0)
        if n > 1:                      # 1종뿐이면 굳이 안 담는다 (용량)
            row["variants_n"] = n
        if b["id"] in light:
            row["light"] = True        # 흰색 로고 — 어두운 배경에 그려야 보인다
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
