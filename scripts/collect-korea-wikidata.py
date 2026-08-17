#!/usr/bin/env python3
"""위키데이터의 '한국 조직 + 공식 로고(P154)' 를 통째로 훑어 신규 브랜드를 모은다.

왜 이게 필요한가 (2026-08-16):
  기존 정규 수집기(Simple Icons·Font Awesome·위키미디어 카테고리)는 포화 상태다.
  ZeroClaw 자동 실행의 신규 수집이 **0건**이었다. 이미 다 가져왔기 때문이지
  고장난 게 아니다. 수백 개를 새로 얻으려면 소스 자체가 바뀌어야 한다.

  실측: 위키데이터에 '국가=대한민국 + 공식로고' 항목이 971개 있고, 우리가
  아직 없는 것이 657개(SVG 362개)다. 전부 한글명을 갖고 있다 — 우리 차별점
  그대로다.

무엇을 거르는가 — 원본에 오류가 섞여 있다. 표본에서 실제로 나온 것들:
  롯데하이마트 → "Lotte Mart 2018.svg"   (다른 회사 로고. 위키데이터 쪽 오류)
  112          → gov.it                  (이탈리아 긴급번호가 한국으로 분류됨)
  닌텐도 와이파이 커넥션 → nintendo.com      (한국 조직이 아님)

  그래서 외국 국가코드 도메인을 빼고, 파일명이 브랜드명과 아무 관계가
  없으면 자동 반영하지 않고 검수 대상으로 뺀다.

기본값은 운영 DB 를 바꾸지 않는다. 스테이징에 받고 지표를 낸다.

사용:
  python3 scripts/collect-korea-wikidata.py --limit 40            # 조사만
  python3 scripts/collect-korea-wikidata.py --download --limit 40 # 스테이징에 받기
  python3 scripts/collect-korea-wikidata.py --download --apply    # 검증 통과분 반영
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from assetguard import safe_write  # noqa: E402

BASE = SCRIPT_DIR.parent / "_clients"
BRANDS = BASE / "brands.json"
STAGE_ROOT = SCRIPT_DIR.parent / "_staging"
REPORT = BASE / "korea-wikidata-report.json"
QUEUE = BASE / "korea-wikidata-review.json"

FETCH_ERRORS: dict[str, int] = {}
UA = {"User-Agent": "semologo-bot/1.0 (https://semologo.com; vibers.leo@gmail.com)"}
MULTI_TLD = {"co.kr", "or.kr", "ne.kr", "go.kr", "re.kr", "ac.kr", "pe.kr"}
# 국가에 매이지 않는 TLD. 여기 속하면 한국 브랜드일 수 있으므로 통과시킨다.
GENERIC_TLD = {"com", "net", "org", "io", "co", "ai", "app", "dev", "me", "tv",
               "info", "biz", "shop", "store", "cloud", "tech", "xyz", "edu", "gov"}

# ── 수집 축(preset) ─────────────────────────────────────────────
# 처음엔 '국가=대한민국' 하나로 고정돼 있었다. 그러면 디즈니·폭스 같은 해외
# 영화사나 글로벌 투자사는 **애초에 들어올 수가 없다.** 축을 바꿔 끼운다.
#
# each preset: (설명, WHERE 절, 한글명 필수 여부, 한국 도메인만 여부)
#   한글명 필수: 한국 대상은 켠다(우리 차별점). 해외 스튜디오·투자사는 끈다 —
#   한글 라벨이 없다고 디즈니를 버릴 이유가 없다.
#   한국 도메인만: 한국 프리셋은 외국 국가코드 도메인을 버린다. 전세계 대상에
#   이걸 켜면 수집 대상이 통째로 사라지므로 프리셋마다 따로 정한다.
PRESETS: dict[str, tuple[str, str, bool, bool]] = {
    "korea": ("한국 조직 전반",
              "?item wdt:P17 wd:Q884 ; wdt:P154 ?logo .", True, True),

    # 전세계 — SVG 로고와 공식 웹사이트를 **둘 다** 가진 항목.
    # 웹사이트를 필수로 두는 이유는 두 가지다. ①우리 도메인 검증 가드를 그대로
    # 태울 수 있다 ②사이트가 없는 항목은 대개 소멸했거나 실체가 희미하다.
    # 실측 55,601개(2026-08-18). 한 번에 받으면 WDQS 가 시간초과 나므로
    # MD5 로 16조각 내어 받는다 — 조각당 7,400행/10초.
    "global": ("전세계 — SVG 로고 + 공식 웹사이트 보유",
               "?item wdt:P154 ?logo ; wdt:P856 ?anysite ."
               ' FILTER(STRENDS(LCASE(STR(?logo)),".svg"))', False, False),

    # 해산한 정당을 빼야 한다. 안 그러면 민주노동당·신민당·선진통일당 같은
    # 옛 정당이 잔뜩 들어온다(실측: 58건 중 36건이 해산).
    "party": ("현존 정당 (한국)",
              "?item wdt:P31/wdt:P279* wd:Q7278 ; wdt:P17 wd:Q884 ; wdt:P154 ?logo ."
              " FILTER NOT EXISTS { ?item wdt:P576 ?dissolved }", True, True),

    "idol": ("K-pop 그룹",
             "?item wdt:P31/wdt:P279* wd:Q215380 ; wdt:P495 wd:Q884 ; wdt:P154 ?logo .", False, False),

    "film": ("영화 제작사 (전세계)",
             "?item wdt:P31/wdt:P279* wd:Q1762059 ; wdt:P154 ?logo .", False, False),

    "investor": ("투자사 (벤처캐피털·투자은행·사모펀드)",
                 "VALUES ?cls { wd:Q3487908 wd:Q319845 wd:Q5418962 wd:Q4230006 }"
                 " ?item wdt:P31/wdt:P279* ?cls ; wdt:P154 ?logo .", False, False),

    # 중앙부처는 정부상징 통일 체계라 대부분 이미 있다. 빠진 건 자체 CI 를 쓰는
    # 공공기관·공기업(공단·공사)이라 그 분류를 함께 넣는다 (실측 115개, SVG 85).
    "public": ("공공기관·공기업 (한국)",
               "VALUES ?cls { wd:Q327333 wd:Q2659904 wd:Q15916930 wd:Q270791 "
               "wd:Q11032611 wd:Q15911314 wd:Q163740 }"
               " ?item wdt:P31/wdt:P279* ?cls ; wdt:P17 wd:Q884 ; wdt:P154 ?logo .", True, True),
}

# 분류(P31)·산업(P452)까지 한 질의에 넣으면 **교차곱으로 행이 폭증**한다.
# 전세계 대상에서 5.2만 항목이 20.9만 행이 되면서 WDQS 가 60초 한도를 넘겨
# 504 를 뱉었다. MD5 로 잘게 쪼개도 소용없었다 — 조각마다 같은 조인을 하기
# 때문이다. 분류를 빼면 **전량 64,183행이 20초**에 들어온다(실측 2026-08-18).
#
# 그래서 큰 프리셋은 2단계로 간다:
#   1단계 코어(항목·로고·사이트·이름) → 중복·가드로 후보를 걸러낸 뒤
#   2단계 그 후보의 QID 만 모아 분류·산업을 배치로 받는다

# ── 수집 우선순위 ─────────────────────────────────────────────
# 5만 개를 한 번에 못 넣고 중간에 멈출 수도 있으므로 **순서가 곧 품질**이다.
#
# 지명도(위키백과 언어판 수)만으로 정렬했더니 상위 48개 중 37개가 **도시**였다
# (아부다비·암스테르담·도쿄…). 언어판 수는 백과사전적 유명도라 도시가
# 압도적으로 유리하다. 진짜 로고이긴 하지만 "브랜드가 다 있다"는 체감과는 다르다.
# 그래서 분류(P31)로 계층을 먼저 나누고, 계층 안에서 지명도로 정렬한다.
CLASS_TIER: dict[str, int] = {}
for _tier, _qids in {
    # 1계층 — 기업·브랜드·서비스. 사람들이 '로고'라고 하면 먼저 떠올리는 것들
    1: ("Q4830453 Q6881511 Q891723 Q783794 Q431289 Q167270 Q507619 Q18043413 "
        "Q786820 Q22687 Q46970 Q658255 Q219577 Q740752 Q18127 Q210167 Q2085381 "
        "Q1320047 Q45400320 Q341 Q7397 Q620615 Q166142 Q506883"),
    # 2계층 — 미디어·조직·스포츠
    2: ("Q1616075 Q14350 Q2001305 Q561068 Q11032 Q1110794 Q41298 Q1002697 "
        "Q1153191 Q43229 Q163740 Q327333 Q157031 Q708676 Q31855 Q1666019 Q35127 "
        "Q7278 Q476028 Q847017 Q2367225 Q215380"),
    # 3계층 — 교육·의료·문화 시설
    3: ("Q3918 Q875538 Q902104 Q23002039 Q23002054 Q16917 Q33506"),
    # 4계층 — 작품·시설. 로고는 있지만 '브랜드'로는 가장 약하다
    4: ("Q5398426 Q7889 Q11424 Q55488 Q94993988 Q7835189"),
}.items():
    for _q in _qids.split():
        CLASS_TIER[_q] = _tier

# 아예 안 받는 분류. 브랜드가 아니고 목록만 흐린다.
CLASS_SKIP = {
    "Q10876391",   # 위키백과 언어판 (339건)
}
# 장소는 장소로 취급한다. 계층을 '가장 낮은 값'으로 정하면 분류가 하나만
# 튀어도 끌려온다 — 파르두비체(체코 도시)에 '출판사' 분류가 붙어 있어서
# 1계층 기업들 사이에 껴 있었다. 아래 분류가 하나라도 있으면 무조건 강등한다.
CLASS_DEMOTE = set("""
Q515 Q3957 Q486972 Q1549591 Q5119 Q6256 Q35657 Q10864048 Q56061 Q15284
Q532 Q262166 Q1637706 Q1093829 Q1187811 Q747074 Q3957 Q17343829
""".split())
DEMOTED_TIER = 4

DEFAULT_TIER = 3   # 분류를 모르면 중간에 둔다

SPARQL_CORE = """SELECT ?item ?ko ?en ?logo ?site ?n WHERE {
  %(where)s
  OPTIONAL { ?item wikibase:sitelinks ?n }
  OPTIONAL { ?item rdfs:label ?ko FILTER(LANG(?ko)="ko") }
  OPTIONAL { ?item rdfs:label ?en FILTER(LANG(?en)="en") }
}"""

SPARQL_KINDS = """SELECT ?item ?kindLabel ?industryLabel WHERE {
  VALUES ?item { %(values)s }
  OPTIONAL { ?item wdt:P31 ?kind }
  OPTIONAL { ?item wdt:P452 ?industry }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ko,en". }
}"""

SPARQL_TEMPLATE = """SELECT ?item ?ko ?en ?logo ?site ?kindLabel ?industryLabel WHERE {
  %(where)s
  OPTIONAL { ?item wdt:P856 ?site }
  OPTIONAL { ?item wdt:P31 ?kind }
  OPTIONAL { ?item wdt:P452 ?industry }
  OPTIONAL { ?item rdfs:label ?ko FILTER(LANG(?ko)="ko") }
  OPTIONAL { ?item rdfs:label ?en FILTER(LANG(?en)="en") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ko,en". }
}"""


def registrable(url: str) -> str:
    if not url:
        return ""
    host = (urllib.parse.urlparse(url if "//" in url else f"//{url}").netloc or url)
    host = re.sub(r"^www\.", "", host.lower().split(":")[0].strip("/"))
    p = host.split(".")
    if len(p) < 2:
        return host
    return ".".join(p[-3:]) if ".".join(p[-2:]) in MULTI_TLD and len(p) >= 3 else ".".join(p[-2:])


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return re.sub(r"-{2,}", "-", s)


def tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) > 2}


# 위키데이터 분류(P31)를 우리 카테고리로 옮긴다. 구체적인 것부터 본다.
# '사업'·'기업'·'상장 기업'·'회사' 는 절반 가까이에 붙어 있어 근거가 못 된다
# (실측 254/144/101/18건) — 이런 건 이름으로 다시 판단한다.
KIND_RULES = [
    ("미디어·엔터", ("레코드 레이블", "연예 기획사", "방송국", "텔레비전 채널", "신문",
                 "걸 그룹", "보이 그룹", "음악 그룹", "아이돌", "영화", "라디오",
                 "미디어", "잡지", "출판사", "가수", "배우")),
    ("게임", ("게임 개발사", "게임 회사", "비디오 게임", "게임 퍼블리셔")),
    ("물류·교통", ("항공사", "지하철 노선", "철도", "rapid transit", "노선", "공항",
                "해운", "물류", "택배", "버스")),
    ("스포츠", ("야구단", "축구단", "스포츠 클럽", "구단", "리그", "체육")),
    ("의료·바이오", ("병원", "제약", "의료기관", "바이오")),
    ("교육", ("대학", "학교", "학원", "교육기관")),
    ("공공·기관", ("정당", "공공기관", "행정각부", "정부 기관", "외청", "지방자치단체",
                "공기업", "군사", "경찰", "위원회", "재단", "협회", "단체", "노동조합")),
    ("금융·결제", ("은행", "보험", "증권", "금융")),
    ("자동차", ("자동차 제조사", "자동차")),
    ("IT·테크", ("웹사이트", "소프트웨어", "포털", "통신사", "인터넷")),
]

# 분류가 일반적일 때 쓰는 이름 기반 보조 규칙
NAME_RULES = [
    ("금융·결제", ("은행", "금융", "보험", "증권", "카드", "캐피탈", "저축")),
    ("의료·바이오", ("병원", "제약", "의료", "바이오", "헬스")),
    ("교육", ("대학", "학교", "교육", "학습", "학원")),
    ("물류·교통", ("항공", "철도", "선", "해운", "물류", "택배", "공항", "고속")),
    ("식품·음료", ("식품", "음료", "커피", "제과", "주류", "우유", "맥주", "라면")),
    ("유통·쇼핑", ("백화점", "마트", "유통", "편의점", "쇼핑", "면세")),
    ("건설·부동산", ("건설", "산업개발", "부동산", "엔지니어링")),
    ("에너지·화학", ("에너지", "화학", "석유", "가스", "전력")),
    ("제조·그룹", ("전자", "중공업", "제조", "정밀", "소재", "지주", "홀딩스")),
    ("미디어·엔터", ("엔터", "방송", "신문", "미디어", "뮤직", "필름")),
]


# 산업분류(P452)가 가장 정확하다 — 안랩→'보안 산업', 이자녹스→'화장품 산업'.
# 분류(P31)는 '기업' 처럼 뭉뚱그린 값이 많아 두 번째로 본다.
INDUSTRY_RULES = [
    ("IT·테크", ("소프트웨어", "computer hardware", "정보기술", "인터넷", "보안", "전자공학",
              "consumer electronics", "반도체", "클라우드", "information technology")),
    ("게임", ("비디오 게임", "게임 산업", "video game")),
    ("자동차", ("자동차 산업", "automotive")),
    ("미디어·엔터", ("음악", "영화", "엔터테인먼트", "entertainment", "방송", "출판", "미디어")),
    ("금융·결제", ("금융", "financial", "은행", "보험", "증권")),
    ("유통·쇼핑", ("소매", "편의점", "retail", "백화점", "전자상거래")),
    ("식품·음료", ("식품", "음료", "커피", "제과", "주류", "외식", "restaurant")),
    ("에너지·화학", ("화학", "석유", "에너지", "전력", "배터리", "가스")),
    ("철강·중공업", ("제철", "조선", "중공업", "철강")),
    ("항공·우주·방산", ("항공우주", "군수", "방위", "aerospace", "defense")),
    ("의료·바이오", ("제약", "바이오", "의료", "헬스케어", "화장품")),
    ("물류·교통", ("물류", "운송", "항공사", "철도", "해운", "택배")),
    ("통신", ("전기통신", "원거리 통신", "telecommunication", "이동통신")),
    ("건설·부동산", ("건설", "부동산", "engineering", "공학")),
]



# 해외 브랜드는 위키데이터에 업종 정보가 거의 없다 — 분류가 '사업'·'기업'
# 뿐이고 산업(P452)은 28% 에만 있다. 그래서 영문 이름의 업종어로 보완한다
# (실측: 스테이징 16,346개 중 21% 를 추가로 분류할 수 있다).
#
# ⚠️ group·corporation·holdings·company 는 **넣지 않는다.** 업종 정보가 아니라
#    법인 형태다. 넣으면 'Zoho Corporation' 이 제조업이 된다.
NAME_RULES_EN = [
    ("금융·결제", "bank banking bancorp insurance assurance capital financial finance "
                "credit securities asset invest bourse"),
    ("물류·교통", "airlines airways aviation logistics shipping express railway railways "
                "transport transit cargo freight seaways ferries"),
    ("의료·바이오", "pharma pharmaceutical pharmaceuticals biotech bioscience biosciences "
                 "health healthcare medical hospital clinic therapeutics diagnostics genomics"),
    ("식품·음료", "foods beverage beverages brewery brewing distillery coffee dairy "
                "confectionery bakery winery"),
    ("유통·쇼핑", "retail supermarket supermarkets hypermarket grocery ecommerce"),
    ("에너지·화학", "energy petroleum petrochemical chemicals chemical refinery solar "
                 "renewables electricity"),
    ("철강·중공업", "steel metallurgical shipbuilding heavy foundry"),
    ("제조·그룹", "manufacturing industries industrial machinery instruments"),
    ("미디어·엔터", "broadcasting broadcaster television radio records recordings music "
                 "studios pictures entertainment publishing publishers newspaper magazine"),
    ("IT·테크", "software technologies semiconductor semiconductors electronics computing "
              "cybersecurity datacenter networks robotics"),
    ("통신", "telecom telecommunications telekom telecommunication wireless"),
    ("자동차", "motors automotive automobiles autoworks"),
    ("건설·부동산", "construction engineering properties realty infrastructure contractors"),
    ("교육", "university universitat universite college academy polytechnic schule"),
    ("스포츠", "athletic athletics stadium"),
    ("게임", "gaming interactive"),
]

def categorize(item: dict) -> str:
    """위키데이터 산업분류(P452) → 분류(P31) → 이름 순으로 카테고리를 고른다.

    억지로 채우지 않는다 — 틀린 카테고리는 목록 필터를 거짓말시킨다.
    """
    industries = " ".join(item.get("industries") or []).lower()
    for cat, words in INDUSTRY_RULES:
        if any(w.lower() in industries for w in words):
            return cat
    kinds = " ".join(item.get("kinds") or [])
    for cat, words in KIND_RULES:
        if any(w in kinds for w in words):
            return cat
    name = (item.get("ko") or "") + " " + (item.get("en") or "")
    for cat, words in NAME_RULES:
        if any(w in name for w in words):
            return cat
    # 해외 브랜드는 여기까지 오는 비율이 높다 — 위키데이터에 업종 정보가
    # 28% 에만 있기 때문이다. 영문 이름의 업종어로 한 번 더 건진다.
    en_tokens = set(re.split(r"[^a-z0-9]+", (item.get("en") or "").lower()))
    for cat, words in NAME_RULES_EN:
        if en_tokens & set(words.split()):
            return cat
    return "기타"


def initials(name: str) -> str:
    """'Korea National University of Education' → 'knue' (약어 대조용)."""
    words = [w for w in re.split(r"[^A-Za-z]+", name or "") if w and w[0].isupper()]
    return "".join(w[0] for w in words).lower()


def korean_core(name: str) -> str:
    """한글 이름에서 대조에 쓸 알맹이만 남긴다 (공백·괄호주석 제거)."""
    n = re.sub(r"\s*[（(][^）)]*[）)]", "", name or "")
    return re.sub(r"\s+", "", n)


def matches_filename(en: str, fname: str, common: set[str], ko: str = "") -> bool:
    """파일명이 이 브랜드의 것이라고 믿을 만한가.

    처음엔 '흔하지 않은 단어가 하나라도 겹치면 통과'로 했는데 두 방향 모두 틀렸다.
      · 롯데하이마트 ← "Lotte Mart 2018.svg"  ('lotte' 하나로 통과. 다른 회사다)
      · 부산 도시철도 1호선 ← "Busan Metro Line 1.svg"  (완벽히 같은데 단어가
        전부 흔하다는 이유로 탈락. 이런 오탈락이 177건 중 대부분이었다)

    그래서 '겹치는 게 있는가'가 아니라 **'브랜드를 특정하는 말이 파일명에
    빠짐없이 들어 있는가'** 를 본다.
    """
    # 한글 파일명을 먼저 본다. 커먼즈에는 "조국혁신당 로고.svg" 처럼 한글로만
    # 이름 붙은 파일이 많고, 영문 토큰만 대조하면 **완벽히 일치하는데도 전부
    # 떨어진다** (정당 22건 중 13건이 이렇게 검수 큐로 빠졌다).
    core = korean_core(ko)
    if len(core) >= 2 and core in korean_core(fname):
        return True
    if not en:
        return False
    name_t, file_t = tokens(en), tokens(fname)
    if not name_t:
        return False
    # 셋 중 하나라도 만족하면 인정한다. 약어 경로를 뒤에 두면 안 된다 —
    # 'Korea National University of Education' 은 'education' 이 구분력 있는
    # 말이라 첫 분기에서 끝나버려 KNUE 대조까지 못 갔다.
    distinctive = name_t - common
    if distinctive and distinctive <= file_t:
        return True                            # 특정하는 말이 전부 있다
    if name_t <= file_t:
        return True                            # 이름 전체가 파일명에 있다
    ini = initials(en)                          # KNUE logotype.svg ← Korea National…
    return len(ini) >= 3 and ini in file_t


def commons_cdn(filepath_url: str) -> str:
    """Special:FilePath → upload.wikimedia.org 직접 경로.

    `Special:FilePath` 는 커먼즈 웹서버가 리다이렉트로 처리하는 경로라
    레이트리밋이 빡빡하다 — 건당 2.0초에 절반이 429 였다. 커먼즈는 파일명
    (밑줄 형태)의 MD5 앞 1·2자로 디렉토리를 나누므로 CDN 경로를 직접 계산할
    수 있다. 같은 파일이 **건당 0.30초**로 온다(실측 2026-08-18).
    """
    name = urllib.parse.unquote(filepath_url.rsplit("/", 1)[-1]).replace(" ", "_")
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    return (f"https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[:2]}/"
            + urllib.parse.quote(name))


def fetch(url: str, timeout: int = 60, tries: int = 3) -> bytes | None:
    """실패 사유를 삼키지 않는다.

    예전엔 어떤 예외든 None 을 돌려줘서, 429(레이트리밋)로 무더기 실패해도
    '가드 거절'로만 집계됐다. 60개 표본에서 38개가 이렇게 사라졌는데
    원인을 알 방법이 없었다. 사유를 FETCH_ERRORS 에 남기고 재시도한다.
    """
    # 커먼즈 파일이면 CDN 직접 경로를 먼저 쓴다. 실패하면 원래 URL 로 떨어진다
    # (파일명 규칙에서 벗어난 예외가 있을 수 있다).
    targets = [commons_cdn(url), url] if "Special:FilePath" in url else [url]
    last = ""
    for i in range(tries):
        for u in targets:
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code == 404:
                    continue          # 다음 후보 URL 로
                if e.code in (429, 503):
                    # Retry-After 를 지킨다. 무시하고 밀어붙이면 더 오래 막힌다.
                    ra = e.headers.get("Retry-After") if e.headers else None
                    try:
                        wait = min(int(ra), 60) if ra else 4 * (i + 1)
                    except ValueError:
                        wait = 4 * (i + 1)
                    time.sleep(wait)
                    break             # 재시도 라운드로
                break
            except Exception as e:
                last = type(e).__name__
                time.sleep(2 * (i + 1))
                break
        else:
            break
    FETCH_ERRORS[last or "unknown"] = FETCH_ERRORS.get(last or "unknown", 0) + 1
    return None


def sparql_core(where: str, slices: int = 16, tries: int = 4) -> list[dict]:
    """분류를 뺀 가벼운 질의.

    전량(6.4만 행)을 한 번에 받으면 응답이 20MB 를 넘어 **중간에 잘린다**
    (JSONDecodeError 로 나타난다 — 서버 오류로 안 보여서 헷갈린다).
    코어 질의는 조각당 7초로 싸므로 MD5 로 나눠 받는다.

    조각은 디스크에 캐시한다. 한 조각이 실패했다고 앞의 20분을 다시
    받는 일이 없어야 한다 (실제로 두 번 겪었다).
    """
    cache = STAGE_ROOT / "wdqs-cache"
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5((where + SPARQL_CORE).encode()).hexdigest()[:10]
    hexd = "0123456789abcdef"
    prefixes = [hexd[i] for i in range(16)] if slices >= 16 else \
               [hexd[i] for i in range(0, 16, max(16 // max(slices, 1), 1))]

    rows: list[dict] = []
    for i, pref in enumerate(prefixes, 1):
        cf = cache / f"{key}-{pref}.json"
        if cf.exists():
            r = json.loads(cf.read_text())
            rows.extend(r)
            print(f"  조각 {i}/{len(prefixes)} '{pref}' → 캐시 {len(r):,}행  누적 {len(rows):,}", flush=True)
            continue
        q = SPARQL_CORE % {"where": f'{where} FILTER(STRSTARTS(MD5(STR(?item)), "{pref}"))'}
        u = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q})
        req = urllib.request.Request(u, headers={**UA, "Accept": "application/sparql-results+json"})
        last = None
        for t in range(tries):
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    r = json.loads(resp.read())["results"]["bindings"]
                break
            except Exception as e:
                last = e
                # 잘린 응답·시간초과 모두 재시도한다. 조용히 넘기면 그 MD5
                # 범위가 통째로 빠지고, 다음 수집이 영영 못 찾는다.
                print(f"  조각 '{pref}' {type(e).__name__} — {12*(t+1)}초 후 재시도 ({t+1}/{tries-1})")
                time.sleep(12 * (t + 1))
        else:
            raise RuntimeError(f"조각 '{pref}' 조회 실패: {last}")
        cf.write_text(json.dumps(r))
        rows.extend(r)
        print(f"  조각 {i}/{len(prefixes)} '{pref}' → {len(r):,}행  누적 {len(rows):,}", flush=True)
    return rows


def fetch_classes(where: str, slices: int = 16) -> dict[str, set[str]]:
    """항목별 분류(P31) QID 만 받는다. 라벨을 안 붙이면 조각당 5초로 싸다.

    카테고리 판정용이 아니라 **수집 순서를 정하기 위한** 것이다.
    """
    cache = STAGE_ROOT / "wdqs-cache"
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5((where + "P31").encode()).hexdigest()[:10]
    out: dict[str, set[str]] = {}
    for pref in "0123456789abcdef"[:slices] or ["" ]:
        cf = cache / f"cls-{key}-{pref}.json"
        if cf.exists():
            for k, v in json.loads(cf.read_text()).items():
                out.setdefault(k, set()).update(v)
            continue
        q = ("SELECT ?item ?c WHERE { %s ?item wdt:P31 ?c ."
             ' FILTER(STRSTARTS(MD5(STR(?item)), "%s")) }' % (where, pref))
        u = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q})
        req = urllib.request.Request(u, headers={**UA, "Accept": "application/sparql-results+json"})
        got: dict[str, list[str]] = {}
        for t in range(4):
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    for row in json.loads(r.read())["results"]["bindings"]:
                        qid = row["item"]["value"].rsplit("/", 1)[-1]
                        got.setdefault(qid, []).append(row["c"]["value"].rsplit("/", 1)[-1])
                break
            except Exception:
                time.sleep(10 * (t + 1))
        else:
            print(f"  ⚠️ 분류 사전조회 조각 '{pref}' 실패 — 그 범위는 기본 계층으로 둔다")
            continue
        cf.write_text(json.dumps(got))
        for k, v in got.items():
            out.setdefault(k, set()).update(v)
    return out


def enrich_kinds(items: dict, qids: list[str], batch: int = 300) -> None:
    """후보의 분류(P31)·산업(P452)만 배치로 받아 items 에 채운다.

    전체가 아니라 **살아남은 후보에만** 한다. 5만 개 전부에 하면 처음의
    교차곱 문제로 되돌아간다. 배치가 실패해도 카테고리만 덜 정확해질 뿐이라
    수집 자체는 진행한다 — 다만 몇 개가 실패했는지는 반드시 남긴다.
    """
    failed = 0
    for i in range(0, len(qids), batch):
        chunk = qids[i:i + batch]
        values = " ".join(f"wd:{q}" for q in chunk)
        q = SPARQL_KINDS % {"values": values}
        u = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q})
        req = urllib.request.Request(u, headers={**UA, "Accept": "application/sparql-results+json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                rows = json.load(r)["results"]["bindings"]
        except Exception:
            failed += len(chunk)
            continue
        for row in rows:
            qid = row["item"]["value"].rsplit("/", 1)[-1]
            it = items.get(qid)
            if not it:
                continue
            if row.get("kindLabel"):
                it["kinds"].add(row["kindLabel"]["value"])
            if row.get("industryLabel"):
                it["industries"].add(row["industryLabel"]["value"])
        print(f"  분류 보강 {min(i+batch, len(qids)):,}/{len(qids):,}", flush=True)
    if failed:
        print(f"  ⚠️ 분류 보강 실패 {failed:,}건 — 카테고리가 이름 기준으로만 매겨진다")


def sparql_all(where: str, slices: int = 1) -> list[dict]:
    """분할 조회. 큰 프리셋은 한 번에 받으면 WDQS 가 시간초과 난다.

    QID 문자열의 MD5 앞자리로 나눈다 — 결정적이고 고르게 갈라지며,
    OFFSET 페이징과 달리 깊은 오프셋에서 느려지지 않는다.
    조각 하나가 끝내 실패하면 예외를 던진다. 조용히 빠뜨리면 '수집이
    끝났다'고 오해하게 되고, 빠진 조각은 영영 안 들어온다.
    """
    if slices <= 1:
        return sparql(where)
    hexd = "0123456789abcdef"
    step = 16 // slices if slices <= 16 else 1
    prefixes = [hexd[i] for i in range(0, 16, max(step, 1))] if slices <= 16 else \
               [a + b for a in hexd for b in hexd][:slices]
    rows: list[dict] = []
    for i, pref in enumerate(prefixes, 1):
        try:
            r = sparql(f'{where} FILTER(STRSTARTS(MD5(STR(?item)), "{pref}"))')
        except Exception as e:
            # 조각이 커서 시간초과가 나는 경우가 있다. 그 조각만 16등분해
            # 다시 시도한다 — 조용히 건너뛰면 그 범위는 영영 안 들어온다.
            print(f"  조각 '{pref}' 실패({type(e).__name__}) — 16등분해 재시도")
            r = []
            for d in "0123456789abcdef":
                r.extend(sparql(f'{where} FILTER(STRSTARTS(MD5(STR(?item)), "{pref}{d}"))'))
        rows.extend(r)
        print(f"  조각 {i}/{len(prefixes)} (MD5 '{pref}') → {len(r):,}행  누적 {len(rows):,}", flush=True)
    return rows


def sparql(where: str, tries: int = 4) -> list[dict]:
    """위키데이터 질의. 429 는 흔하다 — 장애 중에는 분당 1회까지 조인다.

    조용히 빈 결과를 돌려주면 '수집할 게 없다'로 오해하게 되므로, 끝내
    실패하면 예외를 던진다.
    """
    q = SPARQL_TEMPLATE % {"where": where}
    u = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q})
    req = urllib.request.Request(u, headers={**UA, "Accept": "application/sparql-results+json"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                return json.load(r)["results"]["bindings"]
        except urllib.error.HTTPError as e:
            # 429=레이트리밋, 504=질의 시간초과, 503=일시 장애. 셋 다 재시도로 넘어간다.
            # 504 를 안 잡으면 조각 하나가 죽으면서 수집 전체가 멈춘다(실제로 겪음).
            if e.code in (429, 503, 504) and i < tries - 1:
                wait = (70 if e.code == 429 else 15) * (i + 1)
                print(f"  {e.code} — {wait}초 대기 후 재시도 ({i+1}/{tries-1})")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("위키데이터 질의 실패")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="korea", choices=sorted(PRESETS),
                    help="수집 축. korea|party|idol|film|investor|public")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--jobs", type=int, default=6,
                    help="로고 동시 다운로드 수 (커먼즈 예의상 과하게 올리지 않는다)")
    ap.add_argument("--slices", type=int, default=0,
                    help="WDQS 분할 조회 조각 수 (0=분할 안 함)")
    ap.add_argument("--max-tier", type=int, default=0,
                    help="이 계층까지만 수집 (1=기업·브랜드, 2=+미디어·조직, 3=+교육·의료, 4=전부)")
    ap.add_argument("--min-fame", type=int, default=0,
                    help="위키백과 언어판 수 하한 (0=제한없음). 장기꼬리를 자를 때 쓴다")
    ap.add_argument("--sample", type=int, default=0,
                    help="후보에서 무작위 N개만 (대조 시트 눈검사용)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--two-pass", action="store_true",
                    help="분류를 뺀 코어 질의로 받고 후보에만 분류를 보강한다 (global 기본)")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--apply", action="store_true", help="검증 통과분을 brands.json 에 반영")
    ap.add_argument("--stage-review", action="store_true",
                    help="검수 큐 항목도 스테이징에 받는다 (대조 시트로 눈검사용)")
    ap.add_argument("--apply-ids",
                    help="눈으로 확인한 slug 를 쉼표로 나열해 반영한다 (검수 큐 포함)")
    ap.add_argument("--recategorize", action="store_true",
                    help="이미 반영된 위키미디어 브랜드의 카테고리만 다시 매긴다")
    args = ap.parse_args()

    global STAGE, REPORT, QUEUE
    STAGE = Path(os.environ.get("SEMOLOGO_STAGE", str(STAGE_ROOT / f"wikidata-{args.preset}")))
    REPORT = BASE / f"wikidata-{args.preset}-report.json"
    QUEUE = BASE / f"wikidata-{args.preset}-review.json"

    data = json.loads(BRANDS.read_text())
    brands = data["brands"] if isinstance(data, dict) else data
    have_dom = {registrable(b.get("domain") or b.get("website") or "") for b in brands} - {""}
    # 이름 비교는 정규화해서 한다. 예전엔 그대로 비교해서 **이미 있는 브랜드의
    # 중복을 13개 만들었다** — 수집 당시 기존 항목의 name_ko 가 영문("Naver")이라
    # 새로 가져온 한글명("네이버")과 매칭되지 않았기 때문이다.
    # 별칭까지 넣어야 한글명을 나중에 채운 브랜드도 걸린다.
    def name_key(v: str) -> str:
        return re.sub(r"[\s()（）·]|주식회사|대한민국|주\)", "", (v or "")).strip().lower()

    have_name = set()
    for b in brands:
        for v in [b.get("name_ko"), b.get("name_en"), *(b.get("aliases") or [])]:
            k = name_key(v)
            if len(k) >= 2:
                have_name.add(k)
    have_id = {b["id"] for b in brands}

    label, where, require_ko, korea_only = PRESETS[args.preset]
    # 큰 프리셋은 분류를 뺀 코어 질의로 받는다. 분류까지 한 번에 받으면
    # 교차곱으로 행이 폭증해 WDQS 60초 한도를 넘긴다 (SPARQL_CORE 주석 참고).
    two_pass = args.two_pass or args.preset == "global"
    print(f"위키데이터 조회 중… [{args.preset}] {label}"
          + (" — 코어 질의 후 분류를 따로 받는다" if two_pass else ""))
    rows = sparql_core(where) if two_pass else sparql_all(where, args.slices or 1)
    classes: dict[str, set[str]] = {}
    if two_pass:
        print("분류(P31) 사전 조회 — 수집 순서를 정하기 위한 것")
        classes = fetch_classes(where)
    items: dict[str, dict] = {}
    for r in rows:
        qid = r["item"]["value"].rsplit("/", 1)[-1]
        it = items.setdefault(qid, {
            "qid": qid, "ko": r.get("ko", {}).get("value"), "en": r.get("en", {}).get("value"),
            "logo": r["logo"]["value"], "domain": registrable(r.get("site", {}).get("value", "")),
            "kinds": set(), "industries": set(),
            # 위키백과 언어판 수 = 지명도. 유명한 것부터 넣기 위해 쓴다.
            "fame": int(r.get("n", {}).get("value") or 0),
        })
        if r.get("kindLabel"):
            it["kinds"].add(r["kindLabel"]["value"])
        if r.get("industryLabel"):
            it["industries"].add(r["industryLabel"]["value"])

    # 그룹명·업종어처럼 여러 브랜드에 공통으로 나오는 단어는 매칭 근거가 못 된다.
    # 후보 전체에서 빈도를 세어 4회 이상 나오면 '흔한 단어'로 본다.
    common_tokens = {t for t, n in Counter(
        t for v in items.values() for t in tokens(v.get("en") or "")).items() if n >= 4}

    stats = {"wikidata": len(items), "already_have": 0, "not_kr_domain": 0, "no_korean_name": 0,
             "not_svg": 0, "name_file_mismatch": 0, "candidate": 0,
             "downloaded": 0, "guard_rejected": 0, "applied": 0}
    cands, review, png_wanted = [], [], []

    for it in items.values():
        name = it["ko"] or it["en"]
        if not name:
            stats["no_korean_name"] += 1
            continue
        cand_keys = {name_key(x) for x in (it.get("ko"), it.get("en")) if x}
        if (it["domain"] and it["domain"] in have_dom) or (cand_keys & have_name):
            stats["already_have"] += 1
            continue
        # 외국 국가코드 도메인은 한국 조직이 아닐 가능성이 크다 (112 → gov.it).
        # .com/.org 까지 막으면 안 된다 — 하나은행(hanabank.com)·채널A·아리랑처럼
        # 진짜 한국 브랜드를 통째로 버리게 된다 (실측 334개).
        tld = it["domain"].rsplit(".", 1)[-1] if it["domain"] else ""
        if korea_only and tld and tld not in GENERIC_TLD and not it["domain"].endswith(".kr"):
            stats["not_kr_domain"] += 1
            continue
        if not it["logo"].lower().endswith(".svg"):
            # SVG 가 원본이고 PNG 는 언제든 파생할 수 있다. 반대로 PNG 만 있는 건
            # 애매하므로 **서비스에 넣지 않고 대기 목록에만** 둔다. 나중에 진짜
            # 벡터가 수집되면 — 약간 다른 버전이라도 — 그때 함께 올린다.
            stats["not_svg"] += 1
            png_wanted.append({
                "name_ko": it["ko"], "name_en": it["en"],
                "domain": it["domain"], "category": categorize(it),
                "wikidata": it["qid"], "png_only": urllib.parse.unquote(
                    it["logo"].rsplit("/", 1)[-1]),
            })
            continue
        # 한국 대상은 한글명을 필수로 본다(우리 차별점). 해외 스튜디오·투자사는
        # 한글 라벨이 없다고 버릴 이유가 없다 — 프리셋이 정한다.
        if require_ko and not it["ko"]:
            stats["no_korean_name"] += 1
            continue

        fname = urllib.parse.unquote(it["logo"].rsplit("/", 1)[-1])
        # 파일명이 영문명과 한 단어도 안 겹치면 다른 회사 로고일 수 있다.
        # 단, 겹친 단어가 그룹명처럼 흔한 것뿐이면 인정하지 않는다 —
        # 롯데하이마트에 "Lotte Mart 2018.svg" 가 붙어 있었고 'lotte' 만 겹쳐
        # 통과해버렸다(대조 시트에서 발견). 구분력 있는 단어가 하나는 겹쳐야 한다.
        overlap = matches_filename(it["en"], fname, common_tokens, it.get("ko") or "")
        it["file"] = fname
        it["slug"] = slugify(it["en"] or it["ko"]) or it["qid"].lower()
        # slug 충돌은 **이미 같은 브랜드가 있다는 신호**다. 예전엔 QID 를 붙여
        # 회피했는데, 그 바람에 daum ↔ daum-q493104 같은 중복이 41개 생겼다
        # (기존 항목 이름이 영문이라 이름 대조에도 안 걸렸다).
        if it["slug"] in have_id:
            stats["already_have"] += 1
            continue
        if not overlap:
            stats["name_file_mismatch"] += 1
            review.append({k: v for k, v in it.items() if k not in ("kinds", "industries")} |
                          {"reason": "파일명이 이름과 겹치지 않음 — 다른 회사 로고일 수 있다",
                           "category": categorize(it)})
            continue
        cls = classes.get(it["qid"], set())
        if cls and cls <= CLASS_SKIP:
            stats["skip_class"] = stats.get("skip_class", 0) + 1
            continue
        if cls & CLASS_DEMOTE:
            it["tier"] = DEMOTED_TIER
        else:
            it["tier"] = min((CLASS_TIER.get(c, DEFAULT_TIER) for c in cls), default=DEFAULT_TIER)
        if args.max_tier and it["tier"] > args.max_tier:
            stats["low_tier"] = stats.get("low_tier", 0) + 1
            continue
        if args.min_fame and it.get("fame", 0) < args.min_fame:
            stats["low_fame"] = stats.get("low_fame", 0) + 1
            continue
        stats["candidate"] += 1
        cands.append(it)

    # 지명도(위키백과 언어판 수) 내림차순. 5만 개를 한 번에 다 넣을 수는
    # 없고 중간에 멈출 수도 있으므로, **유명한 것부터** 들어와야 한다.
    # 표본 검사에서 확인했듯 원본에는 드라마·폰 모델·컨퍼런스도 섞여 있는데
    # 그런 항목은 대체로 언어판이 적어 자연히 뒤로 밀린다.
    cands.sort(key=lambda c: (c.get("tier", DEFAULT_TIER), -c.get("fame", 0), c["slug"]))

    if args.sample:
        # 무작위 표본. 앞에서 자르면(--limit) 알파벳 앞쪽만 보게 되어
        # 품질 판단이 왜곡된다. 대조 시트로 눈검사할 때 이걸 쓴다.
        import random as _r
        _r.seed(args.seed)
        cands = _r.sample(cands, min(args.sample, len(cands)))
    if args.limit:
        cands = cands[:args.limit]

    if two_pass and cands:
        # 살아남은 후보에만 분류를 받는다. 카테고리 판정에 필요하기 때문이다.
        print(f"분류·산업 보강 — 후보 {len(cands):,}개")
        enrich_kinds(items, [c["qid"] for c in cands])

    wanted_ids = {x.strip() for x in (args.apply_ids or "").split(",") if x.strip()}
    if args.stage_review or wanted_ids:
        # 검수 큐도 후보로 올린다. 반영은 --apply-ids 로 지목한 것만 된다.
        cands = cands + [r for r in review if r["slug"] not in {c["slug"] for c in cands}]

    if args.download and cands:
        STAGE.mkdir(parents=True, exist_ok=True)
        # 순차로 받으면 4만 건에 몇 시간이 걸린다. 커먼즈는 정상적인
        # User-Agent 를 붙인 소수 병렬은 허용한다 — 과하게 올리지 않는다.
        # 이미 받아 둔 파일은 건너뛴다. 중간에 끊겨도 다시 돌리면 이어진다.
        lock = __import__("threading").Lock()
        n = [0]

        def grab(c):
            dest = STAGE / c["slug"] / "logo.svg"
            if dest.exists() and dest.stat().st_size > 0:
                with lock:
                    stats["downloaded"] += 1
                return
            body = fetch(c["logo"])
            with lock:
                n[0] += 1
                if n[0] % 500 == 0:
                    print(f"  받는 중 {n[0]:,}/{len(cands):,}", flush=True)
            if not body:
                with lock:
                    stats["guard_rejected"] += 1
                c["error"] = "다운로드 실패"
                return
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                # HTML 오류페이지·래스터 내장·빈 파일을 여기서 막는다
                safe_write(dest, body)
                with lock:
                    stats["downloaded"] += 1
            except Exception as e:
                with lock:
                    stats["guard_rejected"] += 1
                c["error"] = f"{type(e).__name__}: {e}"

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            list(ex.map(grab, cands))

    if args.recategorize:
        by_qid = {v["qid"]: v for v in items.values()}
        moved = Counter()
        for b in brands:
            it = by_qid.get(b.get("wikidata"))
            if not it:
                continue
            new_cat = categorize(it | {"en": b.get("name_en")})
            if new_cat != b.get("category"):
                moved[f'{b.get("category")} → {new_cat}'] += 1
                b["category"] = new_cat
        BRANDS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        print("카테고리 재분류:")
        for k, n in moved.most_common(15):
            print(f"  {k:26} {n:>4}")
        print(f"  총 {sum(moved.values())}건 이동")
        return 0

    if args.apply or wanted_ids:
        import hashlib
        seen_hash: dict[str, str] = {}
        pool = [c for c in cands if not wanted_ids or c["slug"] in wanted_ids]
        for c in sorted(pool, key=lambda x: len(x["slug"])):   # 짧은 slug 를 대표로
            src = STAGE / c["slug"] / "logo.svg"
            if not src.exists() or c.get("error"):
                continue
            h = hashlib.sha1(src.read_bytes()).hexdigest()
            # 같은 파일이 여러 항목에 걸려 있다 — 지하철 노선·성모병원 분원처럼
            # 실제로 같은 로고를 쓰는 경우다. 하나만 남긴다.
            if h in seen_hash:
                stats["duplicate"] = stats.get("duplicate", 0) + 1
                continue
            seen_hash[h] = c["slug"]
            if c["slug"] in have_id:
                continue
            dest = BASE / c["slug"] / "logo.svg"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            brands.append({
                # 한글명이 없는 프리셋(해외 영화사·투자사)에서 None 이 그대로 들어가
                # 화면이 죽었다(2026-08-17). 표시 이름은 절대 비우지 않는다.
                "id": c["slug"], "name_ko": c["ko"] or c["en"] or c["slug"],
                "name_en": c["en"] or c["ko"] or c["slug"],
                "category": categorize(c), "folder": f"_clients/{c['slug']}",
                "website": c["domain"], "domain": c["domain"],
                "logo_svg": "logo.svg", "has_svg": True,
                "svg_source": "wikimedia", "wikidata": c["qid"],
                "added_at": time.strftime("%Y-%m-%d"),
                "sources": [{"provider": "wikimedia", "file": "logo.svg",
                             "label": f"위키미디어 커먼즈 ({c['file']})"}],
            })
            have_id.add(c["slug"])
            stats["applied"] += 1
        BRANDS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")

    for k in ("wikidata", "already_have", "not_kr_domain", "no_korean_name", "not_svg",
              "name_file_mismatch", "candidate", "downloaded", "guard_rejected",
              "duplicate", "applied"):
        label = {"wikidata": "위키데이터 한국 조직 로고", "already_have": "이미 보유",
                 "not_kr_domain": "외국 국가코드 도메인(제외)", "no_korean_name": "한글명 없음(제외)",
                 "not_svg": "SVG 아님(제외)", "name_file_mismatch": "파일명 불일치(검수 대기)",
                 "candidate": "수집 후보", "downloaded": "받음", "guard_rejected": "가드 거절",
                 "duplicate": "중복 파일(제외)", "applied": "반영"}[k]
        print(f"  {label:26} {stats.get(k, 0):>5}")

    REPORT.write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%d %H:%M"),
                                  "stats": stats}, ensure_ascii=False, indent=1) + "\n")
    QUEUE.write_text(json.dumps({
        "note": "위키데이터에 로고는 있으나 파일명이 브랜드 영문명과 겹치지 않아 자동 수집하지 "
                "않은 목록. 위키데이터 쪽 연결 오류가 섞여 있다(롯데하이마트→Lotte Mart).",
        "generated_at": time.strftime("%Y-%m-%d"),
        "count": len(review), "items": review[:400],
    }, ensure_ascii=False, indent=1) + "\n")
    # PNG 만 있는 후보를 수집 대기 목록에 합친다 (서비스에는 넣지 않는다)
    wanted_path = BASE / "collect-wanted.json"
    w = json.loads(wanted_path.read_text()) if wanted_path.exists() else {"brands": []}
    have_key = {(x.get("wikidata") or "") + "|" + (x.get("name_ko") or "") for x in w["brands"]}
    fresh = [x for x in png_wanted
             if (x.get("wikidata") or "") + "|" + (x.get("name_ko") or "") not in have_key]
    if fresh and not args.limit:
        w["brands"] += fresh
        w["count"] = len(w["brands"])
        w["generated_at"] = time.strftime("%Y-%m-%d")
        w["note"] = (w.get("note", "") + " / 2026-08-16: 위키데이터에 PNG 로고만 있는 한국 브랜드를 "
                     "추가했다. SVG 가 원본이고 PNG 는 파생할 수 있으므로, 이들은 서비스에 넣지 않고 "
                     "대기시켰다가 진짜 벡터가 수집되면 그때 올린다.")
        wanted_path.write_text(json.dumps(w, ensure_ascii=False, indent=1) + "\n")
    if FETCH_ERRORS:
        print("\n다운로드 실패 사유:")
        for k, v in sorted(FETCH_ERRORS.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}건")
    print(f"\nPNG 만 있는 후보 {len(png_wanted)}건 → 수집 대기 목록에 {len(fresh)}건 추가")
    print(f"스테이징: {STAGE}")
    print(f"검수 대기: {QUEUE.name} ({len(review)}건)")
    if not args.apply:
        print("반영하지 않았다 — 확인 후 --apply 로 반영한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
