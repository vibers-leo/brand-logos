#!/usr/bin/env python3
"""
위키데이터에서 한글 브랜드명을 가져와 채운다 — 도메인이 일치할 때만.

왜 필요한가 (2026-08-16 실측):
  전체 6,838개 중 5,751개(84%)에 한글명이 없다. 한국어·초성 검색이 우리
  차별점인데 그 대상이 6분의 1뿐이라는 뜻이다.

왜 이름 검색만으로는 안 되는가 — 표본 15건에서 5건이 오답이었다:
  neptune.ai  → "해왕성"     (행성)
  Glide       → "반모음"     (음성학 용어)
  ChatBot     → "채터봇"     (다른 제품)
  The Mighty  → "마이티"
  Capacitor   → "축전기"     (전자부품. Ionic Capacitor 가 아니다)

  틀린 한글명은 없느니만 못하다. 검색 결과를 오염시켜 **지금보다 나빠진다.**
  그래서 위키데이터 항목의 공식 웹사이트(P856)가 우리가 아는 도메인과
  같을 때만 자동 반영한다. 같은 표본에서 이 규칙의 오답은 0건이었다.

  이름은 맞는데 도메인이 다른 경우는 버리지 않고 후보 큐에 남긴다.
  (apache.org 처럼 재단 도메인을 쓰는 정답도 여기 섞여 있어서, 자동 반영은
  못 해도 사람이 훑을 값어치는 있다.)

표시 이름(name_ko)은 건드리지 않는다 — 별칭에만 넣는다.
  위키데이터 라벨은 브랜드명이 아니라 문서 제목이다. 실측하면 이렇게 나온다:
    AMD  → "어드밴스트 마이크로 디바이시스"   (정식 법인명. 아무도 이렇게 안 부른다)
    KBS  → "KBS (한국방송공사)"              (괄호가 그대로 붙어 있다)
    JTBC → "JTBC 뉴스룸"                    (프로그램 이름)
  카드 제목을 이렇게 바꾸면 오히려 나빠진다. 별칭은 검색에만 쓰이고 화면에
  안 보이므로, 넣어서 손해 볼 일이 없다. 목록(brands-slim.json)도 별칭을
  싣고 초성 검색까지 별칭을 훑으므로 검색 이득은 그대로 다 얻는다.

사용:
  python3 scripts/fill-korean-names-wikidata.py --dry-run --limit 50
  python3 scripts/fill-korean-names-wikidata.py --limit 500      # 적용
  python3 scripts/fill-korean-names-wikidata.py                  # 전체

중단해도 안전하다 — 진행 상황을 캐시에 남기고 다음 실행이 이어받는다.
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
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"
BRANDS = BASE / "brands.json"
CACHE = BASE / ".wikidata-ko-cache.json"          # 조회 결과 (재실행 시 재사용)
QUEUE = BASE / "korean-name-candidates.json"      # 사람이 봐야 하는 후보
REPORT = BASE / "korean-name-report.json"         # 실행 지표

UA = {"User-Agent": "semologo-bot/1.0 (https://semologo.com; vibers.leo@gmail.com)"}

# 2단계 TLD. 이게 없으면 co.kr 도메인의 등록가능 도메인을 "co.kr" 로 잘못 잡는다.
MULTI_TLD = {
    "co.kr", "or.kr", "ne.kr", "go.kr", "re.kr", "pe.kr", "ac.kr",
    "co.uk", "org.uk", "ac.uk", "gov.uk", "co.jp", "or.jp", "ne.jp",
    "com.au", "com.br", "com.cn", "com.tw", "com.hk", "com.sg", "co.in",
}


def registrable(url: str) -> str:
    """등록가능 도메인(eTLD+1). support.trustpilot.com → trustpilot.com

    전체 호스트로 비교하면 서브도메인을 쓰는 브랜드가 통째로 탈락한다
    (실측: Trustpilot 이 support.trustpilot.com 때문에 불일치로 떨어졌다).
    """
    if not url:
        return ""
    host = urllib.parse.urlparse(url if "//" in url else f"//{url}").netloc or url
    host = host.lower().split(":")[0].strip("/")
    parts = host.split(".")
    if len(parts) < 2:
        return host
    if ".".join(parts[-2:]) in MULTI_TLD and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def has_hangul(s: str) -> bool:
    return any("가" <= c <= "힣" for c in s or "")


def alias_forms(label: str) -> list[str]:
    """위키데이터 라벨을 검색어로 쓸 수 있는 형태들로 푼다.

    "KBS (한국방송공사)" 는 그대로 두면 괄호 때문에 아무 질의에도 안 걸린다.
    괄호 안팎을 각각 별칭으로 낸다.
    """
    out = []
    for part in [label, *re.findall(r"[（(]([^）)]+)[）)]", label),
                 re.sub(r"\s*[（(][^）)]*[）)]", "", label)]:
        p = (part or "").strip()
        if p and has_hangul(p) and len(p) <= 40 and p not in out:
            out.append(p)
    return out


class Wiki:
    """위키데이터 호출. 실패를 빈 결과로 흡수하지 않고 사유를 남긴다."""

    def __init__(self, delay: float = 0.25):
        self.delay = delay
        self.errors: list[str] = []

    def _get(self, url: str, tries: int = 3):
        for i in range(tries):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=25) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 429 and i < tries - 1:
                    time.sleep(3 * (i + 1))
                    continue
                self.errors.append(f"HTTP {e.code} {url[:90]}")
                return None
            except Exception as e:                       # 네트워크·JSON 오류
                if i < tries - 1:
                    time.sleep(1.5 * (i + 1))
                    continue
                self.errors.append(f"{type(e).__name__} {url[:90]}")
                return None
        return None

    def search(self, name: str, limit: int = 5) -> list[dict]:
        q = urllib.parse.urlencode({
            "action": "wbsearchentities", "search": name, "language": "en",
            "uselang": "en", "format": "json", "limit": limit, "type": "item",
        })
        time.sleep(self.delay)
        d = self._get(f"https://www.wikidata.org/w/api.php?{q}")
        return (d or {}).get("search", [])

    def entity(self, qid: str) -> dict | None:
        time.sleep(self.delay)
        d = self._get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
        return (d or {}).get("entities", {}).get(qid)


def official_sites(entity: dict) -> list[str]:
    out = []
    for c in entity.get("claims", {}).get("P856", []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, str):
            out.append(v)
    return out


def korean(entity: dict) -> tuple[str | None, list[str]]:
    label = entity.get("labels", {}).get("ko", {}).get("value")
    aliases = [a["value"] for a in entity.get("aliases", {}).get("ko", [])]
    return label, aliases


def resolve(brand: dict, wiki: Wiki) -> dict:
    """브랜드 하나를 조회한다. 판정 사유를 반드시 함께 돌려준다."""
    name = brand.get("name_en") or brand["id"]
    dom = registrable(brand.get("domain") or brand.get("website") or "")
    hits = wiki.search(name)
    if not hits:
        return {"status": "no_entity", "domain": dom}

    fallback = None                                   # 이름만 맞은 후보 (자동 반영 금지)
    for h in hits:
        ent = wiki.entity(h["id"])
        if not ent:
            continue
        ko, al = korean(ent)
        if fallback is None and ko and has_hangul(ko):
            fallback = {"qid": h["id"], "ko": ko, "aliases": al,
                        "sites": [registrable(s) for s in official_sites(ent)]}
        if dom and any(registrable(s) == dom for s in official_sites(ent)):
            if ko and has_hangul(ko):
                return {"status": "verified", "qid": h["id"], "ko": ko,
                        "aliases": [a for a in al if has_hangul(a)], "domain": dom}
            return {"status": "domain_ok_no_ko", "qid": h["id"], "domain": dom}

    if fallback:
        return {"status": "name_only", "domain": dom, **fallback}
    return {"status": "no_korean", "domain": dom}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="이번 실행에서 조회할 브랜드 수")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delay", type=float, default=0.25)
    ap.add_argument("--refresh", action="store_true", help="캐시를 무시하고 다시 조회")
    args = ap.parse_args()

    data = json.loads(BRANDS.read_text())
    brands = data["brands"] if isinstance(data, dict) else data
    cache = {} if args.refresh or not CACHE.exists() else json.loads(CACHE.read_text())

    def searchable_ko(b: dict) -> bool:
        """한글로 찾을 수 있는가 — 이름이든 별칭이든."""
        return has_hangul(b.get("name_ko") or "") or any(
            has_hangul(a) for a in (b.get("aliases") or []))

    todo = [b for b in brands
            if not searchable_ko(b)
            and (b.get("domain") or b.get("website"))
            and b["id"] not in cache]
    # 한국 브랜드를 먼저 돌린다 — 우리 차별점이 거기 있고 적중률도 높다
    todo.sort(key=lambda b: 0 if registrable(b.get("domain") or b.get("website") or "")
              .endswith(".kr") else 1)
    total_missing = sum(1 for b in brands if not searchable_ko(b))
    if args.limit:
        todo = todo[:args.limit]

    print(f"한글명 없음 {total_missing:,}개 | 도메인 있어 조회 가능 {len(todo):,}개 "
          f"(캐시 {len(cache):,}개 재사용)")

    wiki = Wiki(args.delay)
    for i, b in enumerate(todo, 1):
        cache[b["id"]] = resolve(b, wiki)
        if i % 25 == 0 or i == len(todo):
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
            done = sum(1 for v in cache.values() if v["status"] == "verified")
            print(f"  {i:>5}/{len(todo)}  도메인검증 통과 누적 {done}")

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))

    # ── 반영: 도메인 검증 통과분만 ──
    by_id = {b["id"]: b for b in brands}
    applied, queued = [], []
    for bid, r in cache.items():
        b = by_id.get(bid)
        if not b or searchable_ko(b):
            continue
        if r["status"] == "verified":
            have = b.get("aliases") or []
            cand = [a for a in alias_forms(r["ko"]) + [x for x in r.get("aliases", []) if has_hangul(x)]
                    if a not in have]
            # 짧은 표기가 실제로 사람들이 치는 이름이다. 위키데이터는 프로그램명·
            # 정식법인명까지 다 주므로(JTBC 는 7개) 상위 몇 개만 담는다.
            new = sorted(dict.fromkeys(cand), key=len)[:4]
            if not new:
                continue
            applied.append({"id": bid, "shown_as": b.get("name_ko"), "added": new,
                            "qid": r["qid"], "domain": r["domain"]})
            if not args.dry_run:
                b["aliases"] = have + new
        elif r["status"] == "name_only":
            queued.append({"id": bid, "name_en": b.get("name_en"), "ko": r["ko"],
                           "qid": r["qid"], "our_domain": r["domain"],
                           "wikidata_sites": r.get("sites", [])})

    counts: dict[str, int] = {}
    for r in cache.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print(f"\n조회 {len(cache):,}건")
    for k, label in [("verified", "도메인 검증 통과 (반영)"),
                     ("name_only", "이름만 일치 (후보 큐)"),
                     ("domain_ok_no_ko", "도메인 맞으나 한글 라벨 없음"),
                     ("no_korean", "한글 라벨 없음"),
                     ("no_entity", "위키데이터 항목 없음")]:
        print(f"  {label:28} {counts.get(k, 0):>5}")
    if wiki.errors:
        print(f"  ⚠️ 호출 실패 {len(wiki.errors)}건 — 예: {wiki.errors[0]}")

    if not args.dry_run:
        BRANDS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        QUEUE.write_text(json.dumps({
            "note": "이름은 맞았으나 공식 웹사이트가 우리 도메인과 달라 자동 반영하지 않은 후보. "
                    "재단·모회사 도메인을 쓰는 정답이 섞여 있으니 사람이 확인한다.",
            "generated_at": time.strftime("%Y-%m-%d"),
            "count": len(queued), "candidates": queued,
        }, ensure_ascii=False, indent=1) + "\n")
        REPORT.write_text(json.dumps({
            "generated_at": time.strftime("%Y-%m-%d %H:%M"),
            "total_brands": len(brands), "missing_korean_searchable_before": total_missing,
            "looked_up": len(cache), "counts": counts,
            "applied": len(applied), "queued": len(queued),
            "call_errors": len(wiki.errors),
        }, ensure_ascii=False, indent=1) + "\n")

    print(f"\n{'[dry-run] ' if args.dry_run else ''}반영 {len(applied)}건 | 후보 큐 {len(queued)}건")
    for a in applied[:15]:
        print(f"  {a['id']:26} 표시 {a['shown_as']!r}  + 별칭 {a['added']}")
    if len(applied) > 15:
        print(f"  … 외 {len(applied)-15}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
