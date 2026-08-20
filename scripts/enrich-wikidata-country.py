#!/usr/bin/env python3
"""
brands.json 의 wikidata QID 로 국가(P17)·산업(P452)·분류(P31)를 채운다.

왜 —
40,273개로 늘어난 뒤 카테고리의 37%가 '기타'였고, 국내/해외 구분 필드는
아예 없었다. 이름만 보고 규칙으로 때려맞추면 오분류가 '기타'보다 나쁘다.
QID 가 83%(33,470개)에 붙어 있으므로 Wikidata 에서 사실을 받아온다.

  python3 scripts/enrich-wikidata-country.py            # 캐시에 없는 것만
  python3 scripts/enrich-wikidata-country.py --refresh  # 전부 다시

결과는 _clients/wikidata-facts.json 에 캐시한다(재실행 시 재조회 안 함).
brands.json 반영은 apply-wikidata-facts.py 가 한다 — 조회와 반영을 나눠야
중간에 끊겨도 받아둔 데이터를 안 버린다.
"""
import json, sys, time, urllib.request, urllib.parse
from pathlib import Path

C = Path(__file__).resolve().parent.parent / "_clients"
CACHE = C / "wikidata-facts.json"
UA = "semologo-brand-enrich/1.0 (https://semologo.com; vibers.leo@gmail.com)"
BATCH = 400

def query(qids):
    vals = " ".join(f"wd:{q}" for q in qids)
    q = f"""SELECT ?item ?countryLabel ?industryLabel ?typeLabel WHERE {{
  VALUES ?item {{ {vals} }}
  OPTIONAL {{ ?item wdt:P17 ?country. }}
  OPTIONAL {{ ?item wdt:P452 ?industry. }}
  OPTIONAL {{ ?item wdt:P31 ?type. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ko,en". }}
}}"""
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=180))["results"]["bindings"]
        except Exception as e:
            # 조용히 빈 결과로 넘기면 '국가 없는 브랜드'로 굳어버린다 — 반드시 재시도
            if attempt == 3:
                print(f"    ❌ 배치 실패 ({type(e).__name__}: {str(e)[:60]})", flush=True)
                return None
            time.sleep(5 * (attempt + 1))

def main():
    refresh = "--refresh" in sys.argv
    brands = json.load(open(C / "brands.json"))["brands"]
    cache = {} if refresh else (json.load(open(CACHE)) if CACHE.exists() else {})
    qids = [b["wikidata"] for b in brands if b.get("wikidata") and b["wikidata"] not in cache]
    print(f"QID 보유 {sum(1 for b in brands if b.get('wikidata')):,} / 조회 대상 {len(qids):,}")
    if not qids:
        print("✅ 캐시가 최신이다"); return 0
    fail = 0
    for i in range(0, len(qids), BATCH):
        chunk = qids[i:i + BATCH]
        rows = query(chunk)
        if rows is None:
            fail += len(chunk); continue
        got = {}
        for r in rows:
            qid = r["item"]["value"].rsplit("/", 1)[-1]
            e = got.setdefault(qid, {"country": None, "industry": [], "type": []})
            if "countryLabel" in r: e["country"] = r["countryLabel"]["value"]
            for k, f in (("industryLabel", "industry"), ("typeLabel", "type")):
                v = r.get(k, {}).get("value")
                if v and v not in e[f]: e[f].append(v)
        for q in chunk:                       # 응답 없는 QID 도 기록해야 매번 재조회 안 한다
            cache[q] = got.get(q, {"country": None, "industry": [], "type": []})
        json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
        print(f"  {min(i+BATCH,len(qids)):,}/{len(qids):,}  (국가확보 {sum(1 for v in cache.values() if v['country']):,})", flush=True)
        time.sleep(1)
    print(f"✅ 캐시 {len(cache):,}개" + (f" | ⚠️ 실패 {fail:,}개" if fail else ""))
    return 1 if fail else 0

sys.exit(main())
