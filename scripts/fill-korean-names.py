#!/usr/bin/env python3
"""
한글 이름·별칭 채우기.

왜 필요한가 — 2026-08-11 실측:
  노출 브랜드 6,381개 중 5,340개(84%)의 `name_ko` 에 한글이 한 글자도 없었다.
  `samsung` 의 name_ko 가 "samsung", `naver` 는 "Naver" 였다.
  그래서 **"삼성"으로 검색하면 삼성화재·삼성증권은 나오는데 삼성 본체가 안 나왔다.**
  초성 검색도 한글이 있어야 동작하므로 대표 브랜드에서 통째로 무력했다.

두 가지를 구분한다:
  name_ko   화면에 보이는 정식 이름. 바꾸면 카드·페이지 제목이 바뀐다.
  aliases   검색에만 쓰는 추가 표기. LG·SK 처럼 로마자가 정식인 브랜드는
            이름을 '엘지'로 바꾸면 안 되지만, '엘지 로고'로 검색하는 사람은 실재한다.

사용:
  python3 scripts/fill-korean-names.py --dry-run   # 무엇이 바뀌는지만
  python3 scripts/fill-korean-names.py             # 적용
"""
import json, sys, re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"
BRANDS = BASE / "brands.json"

# ko 를 적으면 표시 이름을 바꾸고, aliases 는 검색어만 추가한다.
# 확신하는 브랜드만 넣는다 — 틀린 한글명은 없느니만 못하다.
FIX = {
    # ── 대기업 그룹 ──
    "samsung":          {"ko": "삼성",       "aliases": ["삼성전자", "Samsung"]},
    "lg":               {"aliases": ["엘지", "LG전자", "엘지전자"]},
    "sk":               {"aliases": ["에스케이", "SK그룹"]},
    "lotte":            {"ko": "롯데"},
    "cj":               {"aliases": ["씨제이", "CJ그룹"]},
    "gs":               {"aliases": ["지에스", "GS그룹"]},
    "hanwha":           {"ko": "한화"},
    "doosan":           {"ko": "두산"},
    "hanjin":           {"ko": "한진"},
    "posco":            {"ko": "포스코"},
    "hyundai-steel":    {"ko": "현대제철"},

    # ── 인터넷·커머스 ──
    "naver":            {"ko": "네이버"},
    "kakao":            {"ko": "카카오"},
    "coupang":          {"ko": "쿠팡"},
    "emart":            {"ko": "이마트"},
    "gmarket":          {"ko": "지마켓", "aliases": ["G마켓"]},

    # ── 게임 ──
    "nexon":            {"ko": "넥슨"},
    "ncsoft":           {"ko": "엔씨소프트", "aliases": ["NC소프트", "엔씨"]},
    "netmarble":        {"ko": "넷마블"},
    "krafton":          {"ko": "크래프톤"},
    "smilegate":        {"ko": "스마일게이트"},

    # ── 금융 ──
    "kakaobank":        {"ko": "카카오뱅크"},
    "kbank":            {"ko": "케이뱅크"},

    # ── 통신·미디어 ──
    "kt":               {"aliases": ["케이티", "KT그룹"]},
    "cgv":              {"aliases": ["씨지브이", "CJ CGV"]},
    "tving":            {"ko": "티빙"},
    "sm-entertainment": {"ko": "SM엔터테인먼트", "aliases": ["에스엠", "SM"]},
    # ⚠️ `starship` 은 스타쉽엔터테인먼트가 아니라 Rust 셸 프롬프트다
    #    (domain=starship.rs, category=IT·테크). `compose` 도 컴포즈커피가
    #    아니라 Docker Compose 다. 이름만 보고 넣었다가 잡았다 —
    #    한글명을 넣기 전에 category 와 domain 을 반드시 확인할 것.

    # ── 제약·식음료 ──
    "yuhan":            {"ko": "유한양행"},

    # ── 방송·기관 (로마자가 정식이라 별칭만) ──
    "kbs-co":           {"aliases": ["한국방송공사"]},
    "mbc-co":           {"aliases": ["문화방송"]},
    "sbs-co":           {"aliases": ["서울방송"]},
    "ebs-co":           {"aliases": ["한국교육방송공사"]},
    "kaist-ac":         {"aliases": ["카이스트", "한국과학기술원"]},
    "29cm-co":          {"aliases": ["이십구센티미터"]},
    # ── 2026-08-11 2차: 금융·핀테크 로고월 대조 ──
    # 파일은 있는데 한글명이 없어 한국인이 검색해도 안 나오던 브랜드들.
    # 전부 category 를 대조해 오탐이 아님을 확인했다.
    "nacf-nonghyup":    {"ko": "농협", "aliases": ["NH농협은행", "농협은행", "NH"]},
    "shinhan-bank":     {"ko": "신한은행", "aliases": ["신한"]},
    "hana-bank":        {"ko": "하나은행", "aliases": ["하나금융", "KEB하나은행"]},
    "nffc-suhyup":      {"ko": "수협", "aliases": ["수협은행", "Sh수협"]},
    "kyobo":            {"ko": "교보생명", "aliases": ["교보"]},
    "hyundai-marine--fire-insurance": {"ko": "현대해상", "aliases": ["현대해상화재보험"]},
    "toss-logo":        {"ko": "토스", "aliases": ["Toss", "비바리퍼블리카"]},
    "sentbe":           {"ko": "센트비"},
    "shinsegae":        {"ko": "신세계", "aliases": ["신세계백화점"]},
    "hanwha-aerospace": {"ko": "한화에어로스페이스", "aliases": ["한화"]},
    "rakuten":          {"ko": "라쿠텐"},
    "mirae-asset-group":{"ko": "미래에셋", "aliases": ["미래에셋증권", "미래에셋그룹"]},
    "gs25-gsretail":    {"aliases": ["지에스25", "GS리테일", "GS25"]},
}

def main():
    dry = "--dry-run" in sys.argv
    data = json.loads(BRANDS.read_text())
    brands = data["brands"] if isinstance(data, dict) else data
    by_id = {b["id"]: b for b in brands}

    changed, missing = [], []
    for bid, fix in FIX.items():
        b = by_id.get(bid)
        if not b:
            missing.append(bid); continue
        before = (b.get("name_ko"), tuple(b.get("aliases") or ()))
        if "ko" in fix:
            b["name_ko"] = fix["ko"]
        if "aliases" in fix:
            # 기존 값이 있으면 합치고 중복을 없앤다 (순서 유지)
            merged = list(dict.fromkeys((b.get("aliases") or []) + fix["aliases"]))
            b["aliases"] = merged
        after = (b.get("name_ko"), tuple(b.get("aliases") or ()))
        if before != after:
            changed.append((bid, before, after))

    for bid, before, after in changed:
        print(f"  {bid:20} {before[0]!r} → {after[0]!r}"
              + (f"  +별칭 {list(after[1])}" if after[1] else ""))
    if missing:
        print(f"\n⚠️ brands.json 에 없는 id {len(missing)}개: {', '.join(missing)}")

    print(f"\n{'(dry-run) ' if dry else ''}변경 {len(changed)}건")
    if not dry and changed:
        BRANDS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        print(f"✅ {BRANDS} 저장")

if __name__ == "__main__":
    main()
