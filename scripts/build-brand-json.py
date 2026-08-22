#!/usr/bin/env python3
"""
브랜드별 단일 JSON(_clients/{id}/brand.json)을 만든다.

왜 —
브랜드 상세 페이지가 brands.json 전체를 받아 쓰고 있었다. 7천 개일 땐 3MB 라
넘어갔지만 4만 개면 **18MB** 다. 문제가 두 가지다:
  ① Next 데이터 캐시는 2MB 초과를 저장하지 않는다 → 렌더마다 다시 받는다
  ② 4만 개 객체를 파싱하면 램다 힙이 수백 MB 로 뛴다

한 브랜드를 그리는 데 필요한 건 그 브랜드 레코드 하나(약 1KB)뿐이다.
파일 4만 개가 늘지만 합쳐도 수십 MB 라 Pages 용량에 여유가 있다.

  python3 scripts/build-brand-json.py           # 바뀐 것만 쓴다
  python3 scripts/build-brand-json.py --check   # 최신인지 확인 (CI용)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--brand", help="특정 브랜드만 동기화 (국소 수집·수정용)")
    args = ap.parse_args()

    brands = json.loads((BASE / "brands.json").read_text())["brands"]
    if args.brand:
        brands = [b for b in brands if b["id"] == args.brand]
        if not brands:
            print(f"❌ 브랜드 없음: {args.brand}")
            return 1
    written = stale = missing = 0

    for b in brands:
        d = BASE / b["id"]
        if not d.is_dir():
            # 폴더가 없으면 에셋 자체가 없는 항목이다. check-assets 가 잡는다.
            missing += 1
            continue
        f = d / "brand.json"
        body = json.dumps(b, ensure_ascii=False, separators=(",", ":"))
        if f.exists() and f.read_text() == body:
            continue
        if args.check:
            stale += 1
            continue
        f.write_text(body)
        written += 1

    if args.check:
        if stale:
            print(f"❌ brand.json 이 brands.json 과 어긋남 {stale:,}건 — "
                  f"python3 scripts/build-brand-json.py 로 갱신한다")
            return 1
        print(f"✅ brand.json 최신 (브랜드 {len(brands):,})")
        return 0

    print(f"✅ brand.json {written:,}개 기록 / 폴더 없음 {missing:,}개 / 총 {len(brands):,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
