#!/usr/bin/env python3
"""위키데이터에서 한국어 레이블을 받아 name_ko 가 없는 브랜드를 채운다.

노출 43,008개 중 31,633개(74%)가 한글명이 없다. 한국 사용자가 검색으로
못 찾는다는 뜻이다. 그중 24,977개에 위키데이터 QID 가 있다 —
사람이 붙인 한국어 레이블이 이미 있을 수 있다.

⚠️ SPARQL 은 POST 로 보낸다. GET 은 URL 길이 제한에 걸린다.

  python3 scripts/fetch-korean-labels.py --fetch
  python3 scripts/fetch-korean-labels.py           # 미리보기
  python3 scripts/fetch-korean-labels.py --apply
"""
import json, os, re, sys, time, urllib.parse, urllib.request

CACHE = "_clients/_wikidata-kolabel.json"
UA = "semologo-kolabel/1.0 (https://semologo.com; vibers.leo@gmail.com)"
han = lambda s: bool(re.search(r"[가-힣]", s or ""))

# 위키데이터 한국어 레이블이 현재 사명보다 낡은 것들
SKIP = {"cj-enm"}   # CJ ENM → 'CJ엔터테인먼트'(옛 사명)

def targets():
    d = json.load(open("_clients/brands.json"))["brands"]
    return [b for b in d if not b.get("hidden") and not b.get("variant_of")
            and not han(b.get("name_ko")) and b.get("wikidata")]

def fetch():
    qs = sorted({b["wikidata"] for b in targets()})
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = [q for q in qs if q not in cache]
    print(f"  QID {len(qs):,} · 캐시 {len(cache):,} · 받을 것 {len(todo):,}", flush=True)
    B = 400
    for i in range(0, len(todo), B):
        ch = todo[i:i+B]
        q = (f"SELECT ?i ?l WHERE {{ VALUES ?i {{ {' '.join('wd:'+x for x in ch)} }} "
             f'?i rdfs:label ?l FILTER(LANG(?l)="ko") }}')
        data = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
        req = urllib.request.Request(
            "https://query.wikidata.org/sparql", data=data,
            headers={"User-Agent": UA, "Accept": "application/sparql-results+json",
                     "Content-Type": "application/x-www-form-urlencoded"})
        rows = None
        for a in range(3):
            try:
                with urllib.request.urlopen(req, timeout=180) as f:
                    rows = json.load(f)["results"]["bindings"]; break
            except Exception as e:
                print(f"   재시도 {a+1} {type(e).__name__}", flush=True); time.sleep(8)
        if rows is None:
            print("   ⛔ 3회 실패 — 중단"); break
        for x in ch: cache.setdefault(x, "")
        for r in rows:
            cache[r["i"]["value"].rsplit("/", 1)[-1]] = r["l"]["value"]
        json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
        print(f"   {min(i+B, len(todo)):,}/{len(todo):,}", flush=True)
        time.sleep(1.2)
    print(f"  ✅ 캐시 {len(cache):,}건 · 한글 있음 {sum(1 for v in cache.values() if han(v)):,}")

def main():
    if "--fetch" in sys.argv: return fetch()
    if not os.path.exists(CACHE): return print("  캐시 없음 — 먼저 --fetch")
    cache = json.load(open(CACHE))
    doc = json.load(open("_clients/brands.json"))
    n = 0; sample = []
    for b in doc["brands"]:
        if b.get("hidden") or b.get("variant_of"): continue
        if han(b.get("name_ko")): continue
        ko = cache.get(b.get("wikidata") or "")
        if not han(ko): continue
        # 한글 레이블이 영문명과 사실상 같으면(로마자 표기) 넣을 값이 없다
        if ko.strip() == (b.get("name_en") or "").strip(): continue
        # 사람이 손으로 정한 이름은 덮지 않는다. 실제로 CJ ENM 이 여기서
        # 'CJ엔터테인먼트'(옛 사명)로 되돌아갈 뻔했다.
        if b.get("category_src") == "manual" or b.get("name_ko_src") == "manual": continue
        if b["id"] in SKIP: continue
        if len(sample) < 20: sample.append((b["id"], b.get("name_en"), ko))
        n += 1
        if "--apply" in sys.argv:
            b["name_ko"] = ko; b["name_ko_src"] = "wikidata-ko"
    for i, en, ko in sample: print(f"   {i[:24]:<26} {str(en)[:24]:<26} → {ko}")
    print(f"\n  채울 수 있는 것 {n:,}건")
    if "--apply" in sys.argv:
        json.dump(doc, open("_clients/brands.json", "w"),
                  ensure_ascii=False, separators=(",", ":"))
        print("  ✅ 적용")

main()
