#!/usr/bin/env python3
"""
wikidata-facts.json 캐시를 brands.json 에 반영한다.

조회(enrich-wikidata-country.py)와 반영을 나눈 이유 —
조회는 수십 분 걸리고 중간에 끊길 수 있다. 한 스크립트로 묶으면 매번 처음부터
받아야 한다. 캐시가 남아 있으면 반영은 몇 초다.

  python3 scripts/apply-wikidata-facts.py --dry-run   # 무엇이 바뀌는지만
  python3 scripts/apply-wikidata-facts.py             # 반영

채우는 것:
  country  '대한민국' 같은 국가명 (Wikidata P17)
  origin   'KR' | 'GLOBAL'  — 국내/해외 필터용

⚠️ 한글명 유무로 국적을 판단하면 안 된다. '스타벅스'는 한글명이 있지만 미국
   브랜드다. 반드시 P17 을 근거로 쓴다.
"""
import json, sys, collections
from pathlib import Path

C = Path(__file__).resolve().parent.parent / "_clients"
KR = {"대한민국", "South Korea", "Republic of Korea"}


# Wikidata 산업(P452)·분류(P31) 라벨 → 세모로고 카테고리.
# 실제 캐시에 나온 라벨 빈도 상위부터 골랐다. 부분일치(in)로 본다.
# ⚠️ '사업'·'기업'·'상장 기업'·'회사'·'브랜드'·'상표'·'웹사이트' 처럼
#    업종을 전혀 알려주지 않는 라벨은 일부러 뺐다 — 넣으면 전부 한 곳에 몰린다.
#    오분류는 '기타'보다 나쁘므로 확실한 것만 매핑한다.
LABEL_MAP = [
    ("미디어·엔터", ["텔레비전", "라디오", "방송", "영화", "레코드 레이블", "음악",
                     "스트리밍", "신문", "잡지", "출판", "저널리즘", "연속간행물",
                     "미디어", "애니메이션", "만화", "밴드", "엔터테인먼트", "광고"]),
    ("게임",       ["비디오 게임", "게임 개발", "video game"]),
    ("IT·테크",    ["소프트웨어", "software", "컴퓨터", "computer", "인터넷", "웹사이트 운영",
                     "전자공학", "전자공업", "정보기술", "클라우드", "consumer electronics",
                     "반도체", "하드웨어", "이커머스", "electronic"]),
    ("AI·머신러닝", ["인공지능", "기계 학습", "artificial intelligence"]),
    ("통신",       ["전기통신", "원거리 통신", "휴대 전화", "telecommunication", "이동통신"]),
    ("금융·결제",  ["은행", "금융", "financial", "보험", "증권", "venture capital",
                     "결제", "핀테크", "자산운용"]),
    ("암호화폐·블록체인", ["암호화폐", "블록체인", "cryptocurrency"]),
    ("유통·쇼핑",  ["소매", "연쇄점", "supermarket", "백화점", "브릭 앤드 모르타르",
                     "retail", "쇼핑", "편의점"]),
    ("식품·음료",  ["식품", "음료", "맥주", "양조", "제과", "레스토랑", "커피",
                     "food", "restaurant", "패스트푸드"]),
    ("자동차",     ["자동차", "automotive", "electric vehicle", "타이어"]),
    ("항공·우주·방산", ["항공사", "항공", "우주", "군수", "방위", "airline", "aerospace"]),
    ("물류·교통",  ["운수", "물류", "철도", "해운", "택배", "logistics", "transport",
                     "버스", "지하철"]),
    ("에너지·화학", ["에너지", "석유", "화학공업", "가스", "전력", "원자력",
                     "gas station", "energy", "petroleum"]),
    ("의료·바이오", ["제약", "의료", "병원", "바이오", "pharmaceutical", "healthcare",
                     "생명공학"]),
    ("뷰티·패션",  ["의류", "패션", "화장품", "섬유", "신발", "명품", "fashion", "cosmetic"]),
    ("건설·부동산", ["건설", "부동산", "건축", "construction", "real estate"]),
    ("철강·중공업", ["철강", "중공업", "조선", "제철", "steel", "shipbuilding"]),
    ("제조·그룹",  ["제조사", "제조업", "지주회사", "복합기업", "manufacturer",
                     "machinery", "기계"]),
    ("교육",       ["교육", "대학", "학교", "university", "education", "학원"]),
    ("스포츠",     ["축구", "야구", "농구", "스포츠", "구단", "football club",
                     "sports club", "리그", "올림픽"]),
    ("숙박·여행",  ["호텔", "숙박", "여행", "관광", "hotel", "tourism", "리조트"]),
    ("공공·기관",  ["정당", "정부", "공공", "지방자치", "비영리", "단체", "협회",
                     "재단", "municipality", "government", "agency", "노동조합",
                     "군대", "경찰", "박물관", "도서관"]),
    ("국가·지역",  ["국가", "도시", "주(", "county", "province", "인구 10만"]),
]

def guess_category(labels):
    """라벨 목록에서 카테고리를 고른다. 확실치 않으면 None."""
    for cat, keys in LABEL_MAP:
        for lb in labels:
            for k in keys:
                if k in lb:
                    return cat
    return None


# ── 국내 판정 보조 신호 ────────────────────────────────────────────
# Wikidata P17 만으로는 348개밖에 안 잡힌다. 카카오·쿠팡·토스·삼성모바일처럼
# QID 가 아예 없거나 P17 이 비어 있는 주요 한국 브랜드가 대거 빠지기 때문이다.
# ⚠️ 순서가 중요하다 — P17 로 '다른 나라'가 확정된 브랜드에는 보조 신호를
#    적용하지 않는다. 안 그러면 '스타벅스(한글명 보유·starbucks.co.kr)'가
#    국내로 뒤집힌다. 보조 신호는 **국가 미확정 브랜드에만** 쓴다.
import re as _re

KR_DOMAIN = _re.compile(r"\.kr$")
KR_NAME   = _re.compile(r"\bkorea|korean\b", _re.I)
KR_PREFIX = (
    "samsung", "lg-", "sk-", "hyundai", "kia", "lotte", "cj-", "gs-", "hanwha",
    "doosan", "posco", "shinhan", "kookmin", "woori", "hana-", "nonghyup",
    "celltrion", "coupang", "kakao", "naver", "nexon", "ncsoft", "netmarble",
    "krafton", "toss", "baemin", "daum", "kt-", "emart", "homeplus", "oliveyoung",
    "amorepacific", "innisfree", "ottogi", "nongshim", "orion", "binggrae",
    "maeil", "pulmuone", "cheiljedang", "hyosung", "kolon", "daelim", "hanjin",
    "asiana", "koreanair", "kbank", "kbstar", "hanatour", "yanolja", "musinsa",
)
KR_EXACT = {"kia", "sk", "lg", "kt", "cj", "gs", "naver", "kakao", "toss", "coupang", "baemin"}

def korean_by_hint(b):
    """국가 미확정 브랜드에만 쓰는 보조 판정. 확실하지 않으면 False."""
    # ⚠️ website 는 보면 안 된다 — 스타벅스는 domain=starbucks.com 인데
    #    website=starbucks.co.kr(한국 지사 사이트)이라 국내로 뒤집힌다.
    #    정식 도메인(domain)만 본다.
    if KR_DOMAIN.search(b.get("domain") or ""):
        return True
    if KR_NAME.search(b.get("name_en") or ""):
        return True
    bid = b["id"]
    if bid in KR_EXACT or any(bid.startswith(p) for p in KR_PREFIX):
        return True
    return False


def main():
    dry = "--dry-run" in sys.argv
    facts = json.load(open(C / "wikidata-facts.json"))
    data = json.load(open(C / "brands.json"))
    brands = data["brands"]

    stat = collections.Counter()
    ind = collections.Counter()
    for b in brands:
        f = facts.get(b.get("wikidata") or "")
        if not f:
            if korean_by_hint(b):
                b["origin"] = "KR"; stat["KR(보조신호)"] += 1
            else:
                stat["QID없음/미조회"] += 1
            continue
        c = f.get("country")
        if not c:
            # P17 이 없을 때만 보조 신호를 본다 (다른 나라로 확정된 건 안 건드린다)
            if korean_by_hint(b):
                b["origin"] = "KR"; stat["KR(보조신호)"] += 1
            else:
                stat["국가정보없음"] += 1
        else:
            b["country"] = c
            b["origin"] = "KR" if c in KR else "GLOBAL"
            stat["KR(P17)" if c in KR else "GLOBAL"] += 1
        labels = (f.get("industry") or []) + (f.get("type") or [])
        for x in labels:
            ind[x] += 1
        # 이미 분류된 브랜드는 건드리지 않는다 — 사람이 골라둔 값이 더 정확하다.
        # '기타'인 것만 Wikidata 근거로 다시 매긴다.
        if (b.get("category") or "기타") == "기타":
            g = guess_category(labels)
            if g:
                b["category"] = g
                stat[f"재분류→{g}"] += 1

    print("=== 국가 반영 결과 ===")
    for k, v in stat.most_common():
        print(f"  {v:>7,}  {k}")
    print(f"\n=== 산업/분류 라벨 상위 30 (카테고리 재분류 재료) ===")
    for k, v in ind.most_common(30):
        print(f"  {v:>6,}  {k}")

    if dry:
        print("\n(dry-run — 저장 안 함)"); return
    json.dump(data, open(C / "brands.json", "w"), ensure_ascii=False, indent=2)
    print(f"\n✅ brands.json 저장 (country/origin 반영 {stat['KR']+stat['GLOBAL']:,}개)")

main()
