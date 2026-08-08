#!/usr/bin/env python3
"""
`{id}-icon` 중복 브랜드를 부모의 '심볼 변형'으로 흡수한다.

문제
----
같은 회사의 심볼 버전이 별도 브랜드로 쪼개져 있다 (`adobe` / `adobe-icon`).
목록에 사실상 같은 브랜드가 두 장씩 뜨고, 부모는 심볼 변형이 없다.
현재 429쌍.

왜 삭제하지 않나
----------------
brands.json 에서 지우면 `/brand/{id}-icon` 정적 페이지 429개가 통째로
404 가 된다. 이미 색인됐거나 어딘가에 임베드돼 있을 수 있어 SEO 손실이 크다.
그래서 **항목은 남기고 `variant_of` 로 표시**한다:

  - 부모: 자식의 logo.svg 를 `sources/` 로 가져와 심볼 변형으로 등록
  - 자식: `variant_of: <부모 id>` 표시 → 목록(grid)에서만 제외, 페이지는 유지
  - 자식 페이지에는 부모로 향하는 canonical 을 건다 (사이트 쪽 처리)

되돌리기: 자식의 `variant_of` 를 지우고 부모 sources[] 에서 해당 항목을
빼면 원상복구된다. 파일은 복사만 하므로 원본은 그대로다.

사용:
  python3 scripts/merge-icon-brands.py --dry-run
  python3 scripts/merge-icon-brands.py
"""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"
BRANDS_JSON = BASE / "brands.json"

# 이름이 이 정도도 안 닮으면 사실 다른 브랜드일 수 있다 → 통합하지 않는다
NAME_SIMILARITY_MIN = 0.6


def norm(s: str) -> str:
    return (s or "").lower().replace(" ", "").replace("-", "").replace("icon", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    data = json.loads(BRANDS_JSON.read_text())
    brands = data["brands"]
    by = {b["id"]: b for b in brands}

    pairs = []
    for bid in list(by):
        if not bid.endswith("-icon"):
            continue
        parent = bid[:-5]
        if parent not in by:
            continue
        if by[bid].get("variant_of"):
            continue                                   # 이미 통합됨
        if not (BASE / bid / "logo.svg").exists():
            continue
        # 오통합 방지 — 이름이 실제로 닮았는지 확인
        a, b_ = norm(by[bid].get("name_en", "")), norm(by[parent].get("name_en", ""))
        if a and b_ and difflib.SequenceMatcher(None, a, b_).ratio() < NAME_SIMILARITY_MIN:
            print(f"  ⚠️  건너뜀 {bid} ↔ {parent} (이름 불일치)")
            continue
        pairs.append((bid, parent))

    if args.limit:
        pairs = pairs[: args.limit]
    print(f"통합 대상 {len(pairs)}쌍")
    if args.dry_run:
        for c, p in pairs[:20]:
            print(f"  {c:28} → {p}")
        return 0

    merged = 0
    for child, parent in pairs:
        pdir, cdir = BASE / parent, BASE / child
        rel = f"sources/{child}.svg"
        dst = pdir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(cdir / "logo.svg", dst)
        # 부모 sources[] 에 심볼로 등록 (매니페스트 생성기가 이걸 읽는다)
        srcs = by[parent].setdefault("sources", [])
        if not any(s.get("file") == rel for s in srcs):
            srcs.append({"provider": f"merged:{child}", "file": rel, "label": "아이콘형"})
        # 자식은 남기되 목록에서 빼고 부모를 가리킨다
        by[child]["variant_of"] = parent
        merged += 1
        if merged % 100 == 0:
            print(f"  ... {merged}쌍", flush=True)

    if merged:
        BRANDS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\n통합 {merged}쌍 — 자식 항목은 남아 있고 variant_of 로 표시됨 (404 없음)")
    print("→ 이어서: scripts/build-logo-variants.py && scripts/build-slim.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
