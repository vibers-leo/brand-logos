#!/usr/bin/env python3
"""위키데이터 P31(분류)로 '기타' 브랜드를 재분류한다.

왜 필요한가 —
카탈로그 43,277개 중 '기타'가 9,639개(22%)였다. 대부분 위키미디어에서
대량 수집한 것이라 카테고리 없이 들어왔다. 그만큼이 탐색·필터에서 사라진다.

⚠️ 만능이 아니다. 위키데이터 P31 상위 분류가 '사업'(3,666) '기업'(1,073)
   '상장 기업'(735) 처럼 일반 명사라 카테고리로 못 쓴다.
   구체적인 분류(음식점·리눅스 배포판·미술관·은행)만 매핑되며
   **실측 적중률은 19%** 다. 나머지는 그대로 '기타'로 둔다 —
   억지로 넣으면 잘못된 카테고리가 더 나쁘다.

⚠️ 위키데이터 SPARQL 은 GET 으로 120개 넘게 보내면 URL 길이 초과로 전량
   실패한다(에러도 HTTPError 하나뿐이라 원인이 안 보인다). POST 를 쓴다.

  python3 scripts/reclassify-from-wikidata.py --dry-run
  python3 scripts/reclassify-from-wikidata.py
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
TYPES = ROOT / "_targets" / "wd-types.json"

RULES = [
    (r"음식점|패스트 ?푸드|카페|커피|레스토랑|주점|베이커리|제과", "식품·음료"),
    (r"식품|음료|맥주|와인|양조|증류|유제품", "식품·음료"),
    (r"은행|보험|증권|금융|신용|Sparkasse|저축|카드사|자산운용", "금융·결제"),
    (r"항공사|공항|철도|지하철|버스|해운|물류|택배|transit|운송", "물류·교통"),
    (r"대학|학교|교육|학원|college|university", "교육"),
    (r"병원|의료|제약|바이오|clinic|hospital", "의료·바이오"),
    (r"방송|채널|신문|잡지|출판|영화|음반|레이블|미술관|박물관|극장|저널|학술지", "미디어·엔터"),
    (r"축구|야구|농구|배구|구단|스타디움|아레나|스포츠|리그", "스포츠"),
    (r"비디오 ?게임|게임 ?회사|게임 개발", "게임"),
    (r"호텔|리조트|숙박|여행사|카지노", "숙박·여행"),
    (r"자동차|automobile|오토바이|타이어", "자동차"),
    (r"석유|가스|전력|발전|에너지|화학|정유|광업", "에너지·화학"),
    (r"건설|건축|부동산|시멘트", "건설·부동산"),
    (r"소프트웨어|리눅스|운영체제|웹사이트|인터넷|기술 ?회사|닷컴|전자|반도체|스마트폰|프로그래밍", "IT·테크"),
    (r"백화점|마트|소매|유통|전자상거래|쇼핑", "유통·쇼핑"),
    (r"화장품|패션|의류|보석|시계", "뷰티·패션"),
    (r"정부|부처|청$|관청|지방자치|의회|공공|기관|위원회|협회|연구 ?기관|"
     r"보호 ?지역|공원|regional parliament|Stadtwerk", "공공·기관"),
    (r"철강|조선|중공업|기계", "철강·중공업"),
    (r"항공우주|방위|군수", "항공·우주·방산"),
    (r"암호화폐|블록체인", "암호화폐·블록체인"),
    (r"통신사|이동통신", "통신"),
]


def category_of(types):
    for t in types:
        for pat, c in RULES:
            if re.search(pat, t, re.I):
                return c
    return None


def main():
    dry = "--dry-run" in sys.argv
    if not TYPES.exists():
        print(f"❌ {TYPES.name} 이 없다 — 위키데이터 분류를 먼저 받아야 한다")
        return 1
    types = json.loads(TYPES.read_text())
    doc = json.loads((C / "brands.json").read_text())
    bl = doc["brands"] if isinstance(doc, dict) else doc

    n = Counter()
    for b in bl:
        if b.get("category") != "기타":
            continue
        q = b.get("wikidata")
        if not q or q not in types:
            continue
        c = category_of(types[q])
        if c and c != "기타":
            if not dry:
                b["category"] = c
            n[c] += 1

    total = sum(n.values())
    left = sum(1 for b in bl if b.get("category") == "기타") - (0 if dry else 0)
    print(f"{'[미적용] ' if dry else ''}재분류 {total:,}건")
    for k, v in n.most_common():
        print(f"   {k:<16} {v:,}")
    if not dry:
        (C / "brands.json").write_text(
            json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
        left = sum(1 for b in bl if b.get("category") == "기타")
        print(f"남은 기타 {left:,}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
