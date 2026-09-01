#!/usr/bin/env python3
"""같은 로고 파일을 쓰는 **같은 브랜드 중복 등록**을 하나로 합친다.

같은 회사가 두 번 등록돼 목록에 똑같은 카드가 두 장 뜬다.
`cgv`/`cj-cgv`, `ahnlab`/`ahnlab-inc`, `socket_io`/`socket.io` …

지우지 않고 `variant_of` 로 부모에 흡수한다. 자식 페이지는 살아 있고
canonical 이 부모를 가리킨다 — 이미 색인된 URL 을 잃지 않는다.

**부모는 검색될 id 여야 한다.** 처음엔 '한글명 있는 쪽'을 부모로 했는데
`korail` → `kr-korail`, `cgv` → `cj-cgv` 처럼 사람이 실제로 검색하는
짧은 id 가 자식이 됐다. 그래서 기준을 바꿨다:
  · 수집 흔적(logo-*·kr-*)과 접미사(-ci·-wordmark·-icon·연도)가 없는 쪽
  · 그다음 짧은 쪽
부모에 없는 정보(한글명·웹사이트)는 자식에서 끌어와 채운다.

  python3 scripts/absorb-duplicate-brands.py
  python3 scripts/absorb-duplicate-brands.py --apply
"""
import json, re, sys

FILL = ("name_ko", "website", "domain", "wikidata", "category")

def penalty(i):
    p = 0
    if re.match(r"^(logo|kr)[-_]", i): p += 100
    if re.search(r"-(ci|wordmark|icon)$", i): p += 80
    if re.search(r"-?\d{4}", i): p += 60
    if "--" in i: p += 50      # 연속 하이픈은 '&'·공백을 흘린 수집 흔적이다
    return p

def pick(A, B):
    """(부모, 자식)"""
    ka, kb = penalty(A["id"]), penalty(B["id"])
    if ka != kb: return (A, B) if ka < kb else (B, A)
    return (A, B) if len(A["id"]) <= len(B["id"]) else (B, A)

def main():
    pairs = json.load(open("/tmp/dup-confirmed.json"))
    doc = json.load(open("_clients/brands.json"))
    bs = {b["id"]: b for b in doc["brands"]}
    plan = []
    for a, b in pairs:
        A, B = bs.get(a), bs.get(b)
        if not A or not B: continue
        if A.get("hidden") or B.get("hidden"): continue
        if A.get("variant_of") or B.get("variant_of"): continue
        P, C = pick(A, B)
        filled = [k for k in FILL if not P.get(k) and C.get(k)]
        plan.append((C["id"], P["id"], filled))
    print(f"  흡수 {len(plan)}건")
    for c, p, f in plan:
        note = f"  ← {','.join(f)} 채움" if f else ""
        print(f"   {c[:26]:<28} → {p[:26]:<28}{note}")
    if "--apply" in sys.argv:
        n = fills = 0
        for c, p, f in plan:
            C, P = bs[c], bs[p]
            for k in f:
                P[k] = C[k]; fills += 1
            C["variant_of"] = p
            n += 1
        json.dump(doc, open("_clients/brands.json", "w"),
                  ensure_ascii=False, separators=(",", ":"))
        print(f"  ✅ {n}건 흡수 · 부모 정보 {fills}개 보강")

main()
