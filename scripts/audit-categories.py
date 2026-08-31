#!/usr/bin/env python3
"""현재 카테고리와 위키데이터 설명문이 **정면으로 어긋나는** 것을 찾는다.

BTS(방탄소년단)가 '암호화폐·블록체인'에 있었다. BTS 라는 티커를 가진
토큰과 이름이 겹쳐서 심볼 아이콘 세트를 수집할 때 섞인 것이다.
같은 자리에 유니티(게임 엔진)도 있었다.

이런 건 규칙으로 못 막는다. 이름이 같으니까. 대신 **위키데이터가
뭐라고 하는지** 보면 바로 드러난다 — "South Korean musical group".

⚠️ '설명문이 현재 카테고리와 안 맞는다'만으로는 오탐이 쏟아진다.
   설명문이 **다른 카테고리를 분명히 가리킬 때만** 보고한다.

  python3 scripts/audit-categories.py
  python3 scripts/audit-categories.py --apply
"""
import json, os, re, sys
from collections import Counter

src = open(os.path.join(os.path.dirname(__file__), "categorize-by-wikidata.py")).read()
g = {}
exec(compile(src.replace("\nmain()", ""), "c", "exec"), g)
DESC_RULES = g["DESC_RULES"]

def main():
    desc = json.load(open("_clients/_wikidata-desc.json"))
    doc = json.load(open("_clients/brands.json"))
    hits = []
    for b in doc["brands"]:
        cur = b.get("category")
        if cur in (None, "기타", "Vibers 생태계"): continue
        # 사람이 손으로 정한 것은 건드리지 않는다
        if b.get("category_src") == "manual": continue
        ds = desc.get(b.get("wikidata") or "", "")
        if not ds: continue
        want = None
        for cc, pat in DESC_RULES:
            if re.search(pat, ds.lower(), re.I): want = cc; break
        if want and want != cur:
            hits.append((b["id"], b.get("name_ko") or b.get("name_en"), cur, want, ds[:52]))
    print(f"  어긋남 {len(hits)}건")
    print("  이동 방향 상위:")
    for (a, bb), k in Counter((h[2], h[3]) for h in hits).most_common(15):
        print(f"     {a:<14} → {bb:<14} {k}")
    if "--list" in sys.argv:
        for h in hits[:60]:
            print(f"   {h[0][:20]:<22} {str(h[1])[:14]:<16} {h[2]:<12} → {h[3]:<12} {h[4]}")
    if "--apply" in sys.argv:
        m = {h[0]: h[3] for h in hits}
        n = 0
        for b in doc["brands"]:
            if b["id"] in m:
                b["category"] = m[b["id"]]; b["category_src"] = "wikidata-audit"; n += 1
        json.dump(doc, open("_clients/brands.json", "w"),
                  ensure_ascii=False, separators=(",", ":"))
        print(f"  ✅ {n}건 이동")

main()
