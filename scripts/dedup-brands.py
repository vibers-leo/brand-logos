#!/usr/bin/env python3
"""
dedup-brands.py — brands.json 중복 브랜드 정리

정리 우선순위:
1. id 완전 중복 → 첫 번째 유지
2. name_en(소문자) 중복:
   a. SVG 있는 쪽 우선
   b. 둘 다 SVG → added_at 오래된 쪽 (수동 데이터 우선)
   c. 같은 날 → id 짧은 쪽

Usage: python3 scripts/dedup-brands.py [--dry-run]
"""

import json
import argparse
from collections import defaultdict
from pathlib import Path

BRANDS_JSON = Path(__file__).parent.parent / "_clients" / "brands.json"


def score(b: dict) -> tuple:
    """낮을수록 우선 (keep)"""
    svg_score = 0 if b.get("logo_svg") is True else 1
    date_score = b.get("added_at", "9999")  # 오래된 날짜 = 작은 값 = 우선
    id_len = len(b["id"])
    return (svg_score, date_score, id_len)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(BRANDS_JSON) as f:
        data = json.load(f)
    brands = data["brands"]

    removed = []
    kept_ids = set()

    # Step 1: id 완전 중복 → 첫 번째만 유지
    seen_ids = {}
    step1_remove = set()
    for i, b in enumerate(brands):
        if b["id"] in seen_ids:
            step1_remove.add(i)
            removed.append(("id_dup", b["id"], b.get("name_en", ""), b["id"]))
        else:
            seen_ids[b["id"]] = i

    # Step 2: name_en 소문자 중복
    name_groups = defaultdict(list)
    for i, b in enumerate(brands):
        if i in step1_remove:
            continue
        name = b.get("name_en", "").lower().strip()
        if name:
            name_groups[name].append((i, b))

    step2_remove = set()
    for name, items in name_groups.items():
        if len(items) == 1:
            continue
        # 정렬: score 낮은 것 = 유지
        items_sorted = sorted(items, key=lambda x: score(x[1]))
        winner_i, winner = items_sorted[0]
        for i, b in items_sorted[1:]:
            step2_remove.add(i)
            removed.append(("name_dup", name, b["id"], winner["id"]))

    all_remove = step1_remove | step2_remove

    # 결과
    print(f"총 브랜드: {len(brands)}")
    print(f"제거 대상: {len(all_remove)}개 (id중복={len(step1_remove)}, name중복={len(step2_remove)})")
    print()
    print("=== 제거 목록 ===")
    for reason, name, remove_id, keep_id in removed:
        tag = "[id중복]" if reason == "id_dup" else "[name중복]"
        print(f"  {tag} 제거: {remove_id:<40} → 유지: {keep_id}  ({name!r})")

    if args.dry_run:
        print(f"\n[DRY RUN] 실제 변경 없음. 정리 후 예상: {len(brands) - len(all_remove)}개")
        return

    cleaned = [b for i, b in enumerate(brands) if i not in all_remove]
    data["brands"] = cleaned

    with open(BRANDS_JSON, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 중복 정리 완료: {len(brands)} → {len(cleaned)}개 (-{len(removed)})")


if __name__ == "__main__":
    main()
