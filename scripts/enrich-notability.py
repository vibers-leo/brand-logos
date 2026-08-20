#!/usr/bin/env python3
"""
Wikidata sitelink 수(= 위키백과 언어판 수)를 받아 인지도 점수로 쓴다.

왜 이 지표인가 —
첫 화면이 '최신순'이라 위키미디어 대량수집분(무명 기관·단체)으로 채워져 있었다.
랜덤으로 바꿔도 38,000개 중 대부분이 무명이라 해결이 안 된다(속도는 6.2ms 로
문제가 아니었다). sitelink 수는 위키백과가 몇 개 언어로 문서를 갖고 있느냐라
인지도 대리 지표로 검증돼 있다 — 실측: 방탄소년단 123판 > 현대자동차 31 >
네이버 26 > 다음 22.

⚠️ props=claims 로 받으면 안 된다. 엔티티당 응답이 수십 KB 라 33,470개에
   2.8시간이 걸린다. props=sitelinks 는 50개 1.6초/62KB 다(실측).

  python3 scripts/enrich-notability.py            # 캐시에 없는 것만
  python3 scripts/enrich-notability.py --refresh  # 전부 다시
"""
import json, sys, time, urllib.request, urllib.parse
from pathlib import Path

C = Path(__file__).resolve().parent.parent / "_clients"
CACHE = C / "wikidata-notability.json"
UA = "semologo-brand-enrich/1.0 (https://semologo.com; vibers.leo@gmail.com)"
BATCH = 50           # wbgetentities 의 상한

def fetch(qids):
    url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbgetentities", "ids": "|".join(qids), "props": "sitelinks", "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=90)).get("entities", {})
        except Exception as e:
            if attempt == 3:
                print(f"    실패 ({type(e).__name__})", flush=True)
                return None
            time.sleep(3 * (attempt + 1))

def main():
    refresh = "--refresh" in sys.argv
    brands = json.load(open(C / "brands.json"))["brands"]
    cache = {} if refresh else (json.load(open(CACHE)) if CACHE.exists() else {})
    todo = [b["wikidata"] for b in brands if b.get("wikidata") and b["wikidata"] not in cache]
    print(f"QID {sum(1 for b in brands if b.get('wikidata')):,} / 조회 대상 {len(todo):,}")
    if not todo:
        print("✅ 캐시가 최신이다"); return 0
    fail = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        ents = fetch(chunk)
        if ents is None:
            fail += len(chunk); continue
        for q in chunk:
            e = ents.get(q)
            # 응답 없는 QID 도 0 으로 기록해야 매번 재조회하지 않는다
            cache[q] = len((e or {}).get("sitelinks") or {})
        if (i // BATCH) % 20 == 0 or i + BATCH >= len(todo):
            json.dump(cache, open(CACHE, "w"))
            print(f"  {min(i+BATCH,len(todo)):,}/{len(todo):,}", flush=True)
    json.dump(cache, open(CACHE, "w"))
    print(f"✅ 캐시 {len(cache):,}개" + (f" | ⚠️ 실패 {fail:,}" if fail else ""))
    return 1 if fail else 0

sys.exit(main())
