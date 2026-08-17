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

UA = {"User-Agent": "semologo-bot/1.0 (https://semologo.com; vibers.leo@gmail.com)"}
MULTI_TLD = {"co.kr", "or.kr", "ne.kr", "go.kr", "re.kr", "ac.kr", "pe.kr"}
# 국가에 매이지 않는 TLD. 여기 속하면 한국 브랜드일 수 있으므로 통과시킨다.
GENERIC_TLD = {"com", "net", "org", "io", "co", "ai", "app", "dev", "me", "tv",
               "info", "biz", "shop", "store", "cloud", "tech", "xyz", "edu", "gov"}

# ── 수집 축(preset) ─────────────────────────────────────────────
# 처음엔 '국가=대한민국' 하나로 고정돼 있었다. 그러면 디즈니·폭스 같은 해외
# 영화사나 글로벌 투자사는 **애초에 들어올 수가 없다.** 축을 바꿔 끼운다.
#
# each preset: (설명, WHERE 절, 한글명 필수 여부)
#   한글명 필수: 한국 대상은 켠다(우리 차별점). 해외 스튜디오·투자사는 끈다 —
#   한글 라벨이 없다고 디즈니를 버릴 이유가 없다.
PRESETS: dict[str, tuple[str, str, bool]] = {
    "korea": ("한국 조직 전반",
              "?item wdt:P17 wd:Q884 ; wdt:P154 ?logo .", True),

    # 해산한 정당을 빼야 한다. 안 그러면 민주노동당·신민당·선진통일당 같은
    # 옛 정당이 잔뜩 들어온다(실측: 58건 중 36건이 해산).
    "party": ("현존 정당 (한국)",
              "?item wdt:P31/wdt:P279* wd:Q7278 ; wdt:P17 wd:Q884 ; wdt:P154 ?logo ."
              " FILTER NOT EXISTS { ?item wdt:P576 ?dissolved }", True),

    "idol": ("K-pop 그룹",
             "?item wdt:P31/wdt:P279* wd:Q215380 ; wdt:P495 wd:Q884 ; wdt:P154 ?logo .", False),

    "film": ("영화 제작사 (전세계)",
             "?item wdt:P31/wdt:P279* wd:Q1762059 ; wdt:P154 ?logo .", False),

    "investor": ("투자사 (벤처캐피털·투자은행·사모펀드)",
                 "VALUES ?cls { wd:Q3487908 wd:Q319845 wd:Q5418962 wd:Q4230006 }"
                 " ?item wdt:P31/wdt:P279* ?cls ; wdt:P154 ?logo .", False),

    # 중앙부처는 정부상징 통일 체계라 대부분 이미 있다. 빠진 건 자체 CI 를 쓰는
    # 공공기관·공기업(공단·공사)이라 그 분류를 함께 넣는다 (실측 115개, SVG 85).
    "public": ("공공기관·공기업 (한국)",
               "VALUES ?cls { wd:Q327333 wd:Q2659904 wd:Q15916930 wd:Q270791 "
               "wd:Q11032611 wd:Q15911314 wd:Q163740 }"
               " ?item wdt:P31/wdt:P279* ?cls ; wdt:P17 wd:Q884 ; wdt:P154 ?logo .", True),
}

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


def fetch(url: str, timeout: int = 60) -> bytes | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


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
            if e.code == 429 and i < tries - 1:
                wait = 70 * (i + 1)
                print(f"  429 — {wait}초 대기 후 재시도 ({i+1}/{tries-1})")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("위키데이터 질의 실패")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="korea", choices=sorted(PRESETS),
                    help="수집 축. korea|party|idol|film|investor|public")
    ap.add_argument("--limit", type=int)
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

    label, where, require_ko = PRESETS[args.preset]
    print(f"위키데이터 조회 중… [{args.preset}] {label}")
    rows = sparql(where)
    items: dict[str, dict] = {}
    for r in rows:
        qid = r["item"]["value"].rsplit("/", 1)[-1]
        it = items.setdefault(qid, {
            "qid": qid, "ko": r.get("ko", {}).get("value"), "en": r.get("en", {}).get("value"),
            "logo": r["logo"]["value"], "domain": registrable(r.get("site", {}).get("value", "")),
            "kinds": set(), "industries": set(),
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
        if tld and tld not in GENERIC_TLD and not it["domain"].endswith(".kr"):
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
        stats["candidate"] += 1
        cands.append(it)

    if args.limit:
        cands = cands[:args.limit]

    wanted_ids = {x.strip() for x in (args.apply_ids or "").split(",") if x.strip()}
    if args.stage_review or wanted_ids:
        # 검수 큐도 후보로 올린다. 반영은 --apply-ids 로 지목한 것만 된다.
        cands = cands + [r for r in review if r["slug"] not in {c["slug"] for c in cands}]

    if args.download and cands:
        STAGE.mkdir(parents=True, exist_ok=True)
        for c in cands:
            body = fetch(it_url := c["logo"])
            if not body:
                stats["guard_rejected"] += 1
                c["error"] = "다운로드 실패"
                continue
            dest = STAGE / c["slug"] / "logo.svg"
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                # HTML 오류페이지·래스터 내장·빈 파일을 여기서 막는다
                safe_write(dest, body)
                stats["downloaded"] += 1
            except Exception as e:
                stats["guard_rejected"] += 1
                c["error"] = f"{type(e).__name__}: {e}"
            time.sleep(0.2)

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
    print(f"\nPNG 만 있는 후보 {len(png_wanted)}건 → 수집 대기 목록에 {len(fresh)}건 추가")
    print(f"스테이징: {STAGE}")
    print(f"검수 대기: {QUEUE.name} ({len(review)}건)")
    if not args.apply:
        print("반영하지 않았다 — 확인 후 --apply 로 반영한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
