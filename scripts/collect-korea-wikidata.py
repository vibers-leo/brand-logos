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
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from assetguard import safe_write  # noqa: E402

BASE = SCRIPT_DIR.parent / "_clients"
BRANDS = BASE / "brands.json"
STAGE = SCRIPT_DIR.parent / "_staging" / "korea-wikidata"
REPORT = BASE / "korea-wikidata-report.json"
QUEUE = BASE / "korea-wikidata-review.json"

UA = {"User-Agent": "semologo-bot/1.0 (https://semologo.com; vibers.leo@gmail.com)"}
MULTI_TLD = {"co.kr", "or.kr", "ne.kr", "go.kr", "re.kr", "ac.kr", "pe.kr"}
# 국가에 매이지 않는 TLD. 여기 속하면 한국 브랜드일 수 있으므로 통과시킨다.
GENERIC_TLD = {"com", "net", "org", "io", "co", "ai", "app", "dev", "me", "tv",
               "info", "biz", "shop", "store", "cloud", "tech", "xyz", "edu", "gov"}

SPARQL = """SELECT ?item ?ko ?en ?logo ?site ?kindLabel WHERE {
  ?item wdt:P17 wd:Q884 ; wdt:P154 ?logo .
  OPTIONAL { ?item wdt:P856 ?site }
  OPTIONAL { ?item wdt:P31 ?kind }
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


def categorize(item: dict) -> str:
    """위키데이터 분류(P31) → 우리 카테고리. 못 맞히면 '기타'.

    억지로 채우지 않는다 — 틀린 카테고리는 목록 필터를 거짓말시킨다.
    """
    kinds = " ".join(item.get("kinds") or [])
    for cat, words in KIND_RULES:
        if any(w in kinds for w in words):
            return cat
    name = (item.get("ko") or "") + " " + (item.get("en") or "")
    for cat, words in NAME_RULES:
        if any(w in name for w in words):
            return cat
    return "기타"


def fetch(url: str, timeout: int = 60) -> bytes | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def sparql() -> list[dict]:
    u = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": SPARQL})
    req = urllib.request.Request(u, headers={**UA, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["results"]["bindings"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--apply", action="store_true", help="검증 통과분을 brands.json 에 반영")
    ap.add_argument("--recategorize", action="store_true",
                    help="이미 반영된 위키미디어 브랜드의 카테고리만 다시 매긴다")
    args = ap.parse_args()

    data = json.loads(BRANDS.read_text())
    brands = data["brands"] if isinstance(data, dict) else data
    have_dom = {registrable(b.get("domain") or b.get("website") or "") for b in brands} - {""}
    have_name = {(b.get("name_ko") or "").strip().lower() for b in brands}
    have_name |= {(b.get("name_en") or "").strip().lower() for b in brands}
    have_id = {b["id"] for b in brands}

    print("위키데이터 조회 중…")
    rows = sparql()
    items: dict[str, dict] = {}
    for r in rows:
        qid = r["item"]["value"].rsplit("/", 1)[-1]
        it = items.setdefault(qid, {
            "qid": qid, "ko": r.get("ko", {}).get("value"), "en": r.get("en", {}).get("value"),
            "logo": r["logo"]["value"], "domain": registrable(r.get("site", {}).get("value", "")),
            "kinds": set(),
        })
        if r.get("kindLabel"):
            it["kinds"].add(r["kindLabel"]["value"])

    # 그룹명·업종어처럼 여러 브랜드에 공통으로 나오는 단어는 매칭 근거가 못 된다.
    # 후보 전체에서 빈도를 세어 4회 이상 나오면 '흔한 단어'로 본다.
    common_tokens = {t for t, n in Counter(
        t for v in items.values() for t in tokens(v.get("en") or "")).items() if n >= 4}

    stats = {"wikidata": len(items), "already_have": 0, "not_kr_domain": 0, "no_korean_name": 0,
             "not_svg": 0, "name_file_mismatch": 0, "candidate": 0,
             "downloaded": 0, "guard_rejected": 0, "applied": 0}
    cands, review = [], []

    for it in items.values():
        name = it["ko"] or it["en"]
        if not name:
            stats["no_korean_name"] += 1
            continue
        if (it["domain"] and it["domain"] in have_dom) or name.strip().lower() in have_name:
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
            stats["not_svg"] += 1
            continue
        if not it["ko"]:
            stats["no_korean_name"] += 1
            continue

        fname = urllib.parse.unquote(it["logo"].rsplit("/", 1)[-1])
        # 파일명이 영문명과 한 단어도 안 겹치면 다른 회사 로고일 수 있다.
        # 단, 겹친 단어가 그룹명처럼 흔한 것뿐이면 인정하지 않는다 —
        # 롯데하이마트에 "Lotte Mart 2018.svg" 가 붙어 있었고 'lotte' 만 겹쳐
        # 통과해버렸다(대조 시트에서 발견). 구분력 있는 단어가 하나는 겹쳐야 한다.
        shared = tokens(fname) & tokens(it["en"] or "") if it["en"] else set()
        overlap = bool(shared - common_tokens)
        it["file"] = fname
        it["slug"] = slugify(it["en"] or it["ko"]) or it["qid"].lower()
        if it["slug"] in have_id:
            it["slug"] = f"{it['slug']}-{it['qid'].lower()}"
        if not overlap:
            stats["name_file_mismatch"] += 1
            review.append({k: v for k, v in it.items() if k != "kinds"} |
                          {"reason": "파일명이 영문명과 겹치지 않음 — 다른 회사 로고일 수 있다"})
            continue
        stats["candidate"] += 1
        cands.append(it)

    if args.limit:
        cands = cands[:args.limit]

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

    if args.apply:
        import hashlib
        seen_hash: dict[str, str] = {}
        for c in sorted(cands, key=lambda x: len(x["slug"])):   # 짧은 slug 를 대표로
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
                "id": c["slug"], "name_ko": c["ko"], "name_en": c["en"] or c["ko"],
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
    print(f"\n스테이징: {STAGE}")
    print(f"검수 대기: {QUEUE.name} ({len(review)}건)")
    if not args.apply:
        print("반영하지 않았다 — 확인 후 --apply 로 반영한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
