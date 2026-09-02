#!/usr/bin/env python3
"""한국 공공기관·정부기관 명단을 위키데이터에서 만든다.

알리오(공공기관 경영정보)가 1순위 후보였지만 **JS 로 그려서 정적 파싱이
안 된다**(tr 0개). 위키데이터는 SPARQL 로 바로 받을 수 있고 홈페이지(P856)도
함께 온다.

여러 유형을 훑는다 — 정부기관 하나만으로는 공사·공단·연구원이 빠진다.

  python3 scripts/build-gov-targets.py
"""
import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "_targets" / "gov.json"
C = Path(__file__).resolve().parent.parent / "_clients"
UA = "semologo-gov/1.0 (https://semologo.com; vibers.leo@gmail.com)"

# (QID, 라벨) — 하위 클래스까지 훑는다
TYPES = [
    ("Q327333",   "정부기관"),
    ("Q2659904",  "정부조직"),
    ("Q1802801",  "공기업"),
    ("Q31855",    "연구기관"),
    ("Q7075",     "도서관"),
    ("Q33506",    "박물관"),
    ("Q483242",   "공공기관"),
]

def sparql(qid):
    q = f"""SELECT ?i ?l ?site WHERE {{
      ?i wdt:P31/wdt:P279* wd:{qid} .
      ?i wdt:P17 wd:Q884 .
      OPTIONAL {{ ?i wdt:P856 ?site }}
      ?i rdfs:label ?l FILTER(LANG(?l)="ko")
    }} LIMIT 1500"""
    data = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
    req = urllib.request.Request("https://query.wikidata.org/sparql", data=data,
        headers={"User-Agent": UA, "Accept": "application/sparql-results+json",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=120) as f:
        return json.load(f)["results"]["bindings"]

def main():
    seen, rows = set(), []
    for qid, label in TYPES:
        try:
            res = sparql(qid)
        except Exception as e:
            print(f"  {label}: ❌ {type(e).__name__}"); continue
        n = 0
        for r in res:
            wd = r["i"]["value"].rsplit("/", 1)[-1]
            if wd in seen: continue
            seen.add(wd)
            rows.append({"name": r["l"]["value"],
                         "site": r.get("site", {}).get("value", ""),
                         "wikidata": wd, "kind": label})
            n += 1
        print(f"  {label}: {len(res)}건 → 신규 {n}")
        time.sleep(1.2)

    # 이미 보유한 것 표시
    d = json.loads((C / "brands.json").read_text())["brands"]
    norm = lambda s: re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())
    known = {norm(b.get("name_ko")) for b in d} | {b.get("wikidata") for b in d if b.get("wikidata")}
    todo = [r for r in rows if norm(r["name"]) not in known and r["wikidata"] not in known]
    withsite = [r for r in todo if r["site"]]
    print(f"\n  전체 {len(rows):,} · 미보유 {len(todo):,} · 그중 홈페이지 보유 {len(withsite):,}")
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
    print(f"  ✅ {OUT.name} 기록")

main()
