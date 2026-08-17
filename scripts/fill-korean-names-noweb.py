#!/usr/bin/env python3
"""도메인이 없는 브랜드에 한글명을 채운다 — 이름+분류+웹사이트 3중 가드.

왜 필요한가 (2026-08-17 실측):
  한글로 못 찾는 브랜드 5,327개 중 **3,632개(68%)가 도메인이 없어**
  기존 도구(fill-korean-names-wikidata.py)가 조회조차 못 했다.
  대부분 Simple Icons 출신 IT 브랜드다 — 한국 개발자가 '도커'·'리액트'로
  찾는 바로 그 무리다.

도메인이 없으면 P856 대조를 못 하므로 다른 가드가 필요하다. 실측으로 고른 것:

  ① 영문 이름이 **정확히** 같을 것 (부분일치 금지)
  ② 분류(P31/P279*)가 조직·제품 계열일 것
     → 해왕성(천체)·축전기(전자부품)·반모음(음운) 같은 오답을 원천 차단
  ③ **공식 웹사이트(P856)가 있을 것**
     → 개념어에는 웹사이트가 없다. 이게 'Vector→벡터', 'Cube→큐브' 같은
       일반명사 오답을 걸러내는 결정적 가드다
  ④ 한글 라벨이 하나뿐일 것 (여럿이면 모호하므로 버린다)
  ⑤ '동음이의' 문서 제외

그래도 **한 단어 이름은 자동 반영하지 않는다.** Vector·Cube·Flight·Harmony
처럼 흔한 영어 단어는 위 가드를 통과해도 위험하다. 검수 파일로 뺀다.
여러 단어로 된 이름(Adobe Illustrator, Google Scholar)은 모호할 여지가 없다.

표시 이름은 바꾸지 않고 **별칭에만** 넣는다 — 화면은 그대로, 검색만 는다.

사용:
  python3 scripts/fill-korean-names-noweb.py            # 조회 → 검수 파일 생성
  python3 scripts/fill-korean-names-noweb.py --apply    # 자동 통과분 반영
  python3 scripts/fill-korean-names-noweb.py --apply-review  # 검수 통과분까지
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"
BRANDS = BASE / "brands.json"
CACHE = BASE / ".wikidata-noweb-cache.json"
REVIEW = BASE / "korean-name-noweb-review.json"

UA = {"User-Agent": "semologo-bot/1.0 (https://semologo.com; vibers.leo@gmail.com)",
      "Accept": "application/sparql-results+json"}

BATCH = 180          # VALUES 절에 넣을 이름 수
PAUSE = 8            # 배치 사이 대기(초). WDQS 는 장애 중 분당 1회까지 조인다

# 조직·제품 계열. 여기 없는 분류(천체·수학개념·음운 등)는 애초에 매치되지 않는다.
CLASSES = ("wd:Q4830453 wd:Q783794 wd:Q43229 wd:Q7397 wd:Q341 wd:Q166142 "
           "wd:Q35127 wd:Q431289 wd:Q9143 wd:Q7889 wd:Q13479982 wd:Q1092563 "
           "wd:Q18388277 wd:Q1058914 wd:Q11032 wd:Q4438121")


def hangul(s: str | None) -> bool:
    return any("가" <= c <= "힣" for c in (s or ""))


def searchable(b: dict) -> bool:
    return hangul(b.get("name_ko")) or any(hangul(a) for a in (b.get("aliases") or []))


def sparql(names: list[str], tries: int = 5) -> list[dict]:
    values = " ".join(f'"{n}"@en' for n in names)
    q = f"""SELECT ?name ?item ?ko WHERE {{
      VALUES ?name {{ {values} }}
      ?item rdfs:label ?name .
      VALUES ?cls {{ {CLASSES} }}
      ?item wdt:P31/wdt:P279* ?cls .
      ?item wdt:P856 ?site .
      ?item rdfs:label ?ko FILTER(LANG(?ko)="ko")
      FILTER(!CONTAINS(?ko, "동음이의"))
    }}"""
    u = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q})
    req = urllib.request.Request(u, headers=UA)
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)["results"]["bindings"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and i < tries - 1:
                wait = 70 * (i + 1)
                print(f"    {e.code} — {wait}초 대기 후 재시도 ({i+1}/{tries-1})")
                time.sleep(wait)
                continue
            raise
        except Exception:
            if i < tries - 1:
                time.sleep(20)
                continue
            raise
    raise RuntimeError("위키데이터 질의 실패")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="여러 단어 이름(자동 통과)만 반영")
    ap.add_argument("--apply-review", action="store_true", help="검수 파일의 한 단어 이름까지 반영")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    data = json.loads(BRANDS.read_text())
    brands = data["brands"] if isinstance(data, dict) else data
    cache: dict[str, str] = ({} if args.refresh or not CACHE.exists()
                             else json.loads(CACHE.read_text()))

    targets = [b for b in brands
               if not searchable(b)
               and not (b.get("domain") or b.get("website"))
               and (b.get("name_en") or "").strip()
               and '"' not in b["name_en"] and len(b["name_en"]) >= 3]
    todo = [b for b in targets if b["name_en"] not in cache]
    if args.limit:
        todo = todo[:args.limit]
    print(f"대상 {len(targets):,}개 (미조회 {len(todo):,}, 캐시 {len(cache):,})")

    names = sorted({b["name_en"] for b in todo})
    for i in range(0, len(names), BATCH):
        part = names[i:i + BATCH]
        rows = sparql(part)
        by_name: dict[str, set[str]] = defaultdict(set)
        for r in rows:
            by_name[r["name"]["value"]].add(r["ko"]["value"])
        for n in part:
            v = by_name.get(n)
            # 후보가 여럿이면 모호하다 — 버린다
            ko = list(v)[0] if v and len(v) == 1 else ""
            # 위키데이터 동음이의 꼬리표는 브랜드명이 아니다 — "LIG (기업)" → "LIG"
            cache[n] = re.sub(r"\s*[（(][^）)]*[）)]\s*$", "", ko).strip()
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
        print(f"  {min(i+BATCH, len(names))}/{len(names)} 조회 "
              f"(누적 확보 {sum(1 for x in cache.values() if x):,})")
        time.sleep(PAUSE)

    auto, review = [], []
    for b in targets:
        ko = cache.get(b["name_en"] or "")
        if not ko or not hangul(ko):
            continue
        if ko in (b.get("aliases") or []):
            continue
        row = {"id": b["id"], "name_en": b["name_en"], "ko": ko, "category": b.get("category")}
        # 한 단어 영문명은 흔한 명사일 수 있다 — 사람이 본 뒤에만 반영한다
        (auto if len(b["name_en"].split()) >= 2 else review).append(row)

    if args.apply or args.apply_review:
        by_id = {b["id"]: b for b in brands}
        picked = auto + (review if args.apply_review else [])
        for r in picked:
            b = by_id[r["id"]]
            b["aliases"] = (b.get("aliases") or []) + [r["ko"]]
        BRANDS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        print(f"\n반영 {len(picked):,}건 (자동 {len(auto)}, 검수 {len(review) if args.apply_review else 0})")
    else:
        REVIEW.write_text(json.dumps({
            "note": "한 단어 영문명이라 자동 반영하지 않은 후보. Vector→벡터 처럼 흔한 "
                    "명사가 섞일 수 있어 사람이 훑는다. 확인 후 --apply-review 로 반영.",
            "generated_at": time.strftime("%Y-%m-%d"),
            "auto_count": len(auto), "review_count": len(review), "items": review,
        }, ensure_ascii=False, indent=1) + "\n")
        print(f"\n자동 반영 가능 {len(auto):,}건 | 검수 필요 {len(review):,}건 → {REVIEW.name}")
        for r in auto[:12]:
            print(f"   {r['name_en'][:28]:30} → {r['ko']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
