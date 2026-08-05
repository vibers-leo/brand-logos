#!/usr/bin/env python3
"""
normalize-categories.py — brands.json 카테고리 정규화
53개 비일관 카테고리 → 22개 표준 카테고리로 통일
Usage: python3 scripts/normalize-categories.py
"""

import json
import os
from collections import defaultdict

BRANDS_JSON = os.path.join(os.path.dirname(__file__), "..", "_clients", "brands.json")

CATEGORY_MAP = {
    # IT·테크
    "전자/IT": "IT·테크", "IT·클라우드": "IT·테크", "개발도구": "IT·테크",
    "소프트웨어·개발": "IT·테크", "기업솔루션": "IT·테크", "협업도구": "IT·테크",
    # AI·머신러닝
    "AI/LLM": "AI·머신러닝", "AI/생산성": "AI·머신러닝", "AI/영상": "AI·머신러닝",
    "AI/음성": "AI·머신러닝", "AI/음악": "AI·머신러닝", "AI/이미지": "AI·머신러닝",
    "AI/코딩": "AI·머신러닝", "AI/텍스트": "AI·머신러닝", "AI/플랫폼": "AI·머신러닝",
    "AI·머신러닝": "AI·머신러닝",
    # 금융·결제
    "금융/보험": "금융·결제", "금융·결제": "금융·결제",
    "핀테크": "금융·결제", "암호화폐·블록체인": "금융·결제",
    # 미디어·엔터
    "미디어": "미디어·엔터", "미디어/광고": "미디어·엔터", "스트리밍": "미디어·엔터",
    "엔터테인먼트": "미디어·엔터", "소셜미디어": "미디어·엔터",
    # 뷰티·패션
    "뷰티/패션": "뷰티·패션", "패션": "뷰티·패션",
    # 식품·음료
    "식품/음료": "식품·음료", "식음료": "식품·음료", "음식배달": "식품·음료",
    # 의료·바이오
    "건강/의료": "의료·바이오", "제약/의료": "의료·바이오",
    # 유통·쇼핑
    "유통/쇼핑": "유통·쇼핑", "이커머스": "유통·쇼핑",
    # 그대로 유지
    "자동차": "자동차", "게임": "게임", "통신": "통신", "반려동물": "반려동물",
    "스포츠": "스포츠",
    # 건설·부동산
    "건설/부동산": "건설·부동산",
    # 제조·그룹
    "제조/그룹": "제조·그룹", "기업": "제조·그룹",
    # 철강·중공업
    "철강/중공업": "철강·중공업", "조선/중공업": "철강·중공업",
    # 에너지·화학
    "에너지/화학": "에너지·화학",
    # 물류·교통
    "물류/교통": "물류·교통", "모빌리티": "물류·교통",
    # 숙박·여행
    "숙박/여행": "숙박·여행", "여행": "숙박·여행", "관광/문화": "숙박·여행",
    # 공공·기관
    "공공/기관": "공공·기관",
    # 라이프스타일
    "완구/라이프스타일": "라이프스타일",
    # 기타
    "기타": "기타", "": "기타",
}


def main():
    print(f"읽는 중: {BRANDS_JSON}")
    with open(BRANDS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    brands = data["brands"]
    print(f"전체 브랜드: {len(brands)}개\n")

    changed, same, no_map = 0, 0, 0
    change_log = defaultdict(lambda: defaultdict(int))
    unmapped = defaultdict(list)
    empty_brands = []

    for b in brands:
        orig = b.get("category", "") or ""
        if orig == "":
            empty_brands.append(b.get("id", "?"))
        if orig in CATEGORY_MAP:
            new = CATEGORY_MAP[orig]
            if orig != new:
                change_log[orig][new] += 1
                changed += 1
            else:
                same += 1
            b["category"] = new
        else:
            unmapped[orig].append(b.get("id", "?"))
            no_map += 1

    print("=" * 56)
    print("카테고리 변경 요약")
    print("=" * 56)
    for old in sorted(change_log):
        for new, cnt in change_log[old].items():
            print(f"  {old:<32} → {new}  ({cnt}개)")

    print(f"\n변경됨: {changed}  이미표준: {same}  매핑없음(유지): {no_map}")

    if unmapped:
        print("\n[⚠ 매핑 없음 — 수동 검토]")
        for cat, ids in sorted(unmapped.items()):
            print(f"  {cat!r}: {len(ids)}개")

    if empty_brands:
        print(f"\n[빈 카테고리 → 기타 처리됨: {len(empty_brands)}개]")
        print("  " + ", ".join(empty_brands[:20]) + ("..." if len(empty_brands) > 20 else ""))

    data["brands"] = brands
    with open(BRANDS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ brands.json 저장 완료")


if __name__ == "__main__":
    main()
