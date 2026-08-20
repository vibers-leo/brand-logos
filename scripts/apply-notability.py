#!/usr/bin/env python3
"""
wikidata-notability.json(=sitelink 수)을 brands.json 의 fame 필드로 반영한다.

fame 은 그리드 기본 정렬(인기순)의 기준이다. 값이 없으면 0 으로 본다 —
없는 것을 중간값으로 채우면 무명 브랜드가 앞으로 올라온다.

  python3 scripts/apply-notability.py --dry-run
  python3 scripts/apply-notability.py
"""
import json, sys, collections
from pathlib import Path

C = Path(__file__).resolve().parent.parent / "_clients"

# 지리·인물 항목은 인기 baseline 에서 뺀다.
#
# 왜 — sitelink 수는 '백과사전적 저명도'라 도시·국가가 압도한다.
# 그대로 쓰면 첫 화면이 파리(366판)·뉴욕(324)·서울(257)로 채워진다.
# 로고 사이트에서 사람들이 찾는 건 브랜드지 도시 문장이 아니다.
# ⚠️ 우리 category 로는 못 거른다 — '파리'가 '미디어·엔터'로 분류돼 있다.
#    Wikidata 의 type(P31) 라벨이 정확하므로 그걸 쓴다.
GEO = ("도시", "municipality", "행정 구역", "주(", "state of", "province", "county",
       "수도", "지방", "군(", "구(", "마을", "섬", "산맥", "강(", "호수", "국가",
       "나라", "공화국", "region", "commune", "village", "town", "district",
       "prefecture", "canton", "관광 명소", "공원", "사람", "인물", "직할시", "특별시")

def is_geo(brand, facts):
    types = (facts.get(brand.get("wikidata") or "") or {}).get("type") or []
    return any(any(g in t for g in GEO) for t in types)


def main():
    dry = "--dry-run" in sys.argv
    fame = json.load(open(C / "wikidata-notability.json"))
    facts_path = C / "wikidata-facts.json"
    facts = json.load(open(facts_path)) if facts_path.exists() else {}
    data = json.load(open(C / "brands.json"))
    brands = data["brands"]

    dist = collections.Counter()
    n = 0
    for b in brands:
        v = fame.get(b.get("wikidata") or "")
        if v and is_geo(b, facts):
            v = 0                   # 지리·인물은 baseline 에서 제외
        if v:                       # 0 은 굳이 싣지 않는다(용량)
            b["fame"] = v; n += 1
        else:
            b.pop("fame", None)
        dist[0 if not v else (1 if v < 3 else (2 if v < 10 else (3 if v < 30 else 4)))] += 1

    label = {0: "0판(무명)", 1: "1~2판", 2: "3~9판", 3: "10~29판", 4: "30판+"}
    print("=== 인지도 분포 ===")
    for k in sorted(dist): print(f"  {dist[k]:>7,}  {label[k]}")

    top = sorted((b for b in brands if b.get("fame")), key=lambda x: -x["fame"])[:15]
    print("\n=== 상위 15 (첫 화면에 뜰 것들) ===")
    for b in top:
        print(f"  {b['fame']:>4}판  {(b.get('name_ko') or b.get('name_en'))[:30]}")

    if dry:
        print("\n(dry-run — 저장 안 함)"); return
    json.dump(data, open(C / "brands.json", "w"), ensure_ascii=False, indent=2)
    print(f"\n✅ brands.json 저장 (fame 반영 {n:,}개)")

main()
