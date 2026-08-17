#!/usr/bin/env python3
"""위키데이터에서 수집한 브랜드에 **공식 별칭**을 채운다 (QID 기준).

왜 필요한가 (2026-08-17 실측):
  KKR 을 수집했는데 `kohlberg-kravis-roberts` / "콜버그 크래비스 로버츠" 로만
  들어가서 **"KKR" 로 검색하면 안 나왔다.** 사람들은 정식 법인명으로 찾지 않는다.

왜 약어를 자동 생성하지 않는가:
  이름 첫 글자를 따면 KMF(Kbc My FM)·TRA(Third ROK Army)·DWP 같은
  아무도 안 쓰는 문자열이 쏟아진다. 검색을 오염시킬 뿐이다.
  위키데이터의 skos:altLabel 은 사람이 넣은 실제 통용 표기다 — 그것만 쓴다.

QID 로 조회하므로 동명이인 위험이 없다 (이름 검색과 다른 점).

사용:
  python3 scripts/backfill-wikidata-aliases.py --dry-run
  python3 scripts/backfill-wikidata-aliases.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"
BRANDS = BASE / "brands.json"
UA = {"User-Agent": "semologo-bot/1.0 (https://semologo.com; vibers.leo@gmail.com)",
      "Accept": "application/sparql-results+json"}

CHUNK = 250          # VALUES 절에 한 번에 넣을 QID 수


def sparql(qids: list[str], tries: int = 4) -> list[dict]:
    values = " ".join(f"wd:{q}" for q in qids)
    q = f"""SELECT ?item ?alias WHERE {{
      VALUES ?item {{ {values} }}
      ?item skos:altLabel ?alias .
      FILTER(LANG(?alias) IN ("ko", "en"))
    }}"""
    u = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q})
    req = urllib.request.Request(u, headers=UA)
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                return json.load(r)["results"]["bindings"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                wait = 70 * (i + 1)
                print(f"  429 — {wait}초 대기 후 재시도")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("위키데이터 질의 실패")


def useful(alias: str, brand: dict) -> bool:
    """검색에 보탬이 되는 별칭인가."""
    a = alias.strip()
    if not (1 < len(a) <= 40):
        return False
    have = {(brand.get("name_ko") or "").lower(), (brand.get("name_en") or "").lower(),
            brand["id"].lower()} | {x.lower() for x in (brand.get("aliases") or [])}
    return a.lower() not in have


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    data = json.loads(BRANDS.read_text())
    brands = data["brands"] if isinstance(data, dict) else data
    targets = [b for b in brands if b.get("wikidata")]
    if args.limit:
        targets = targets[:args.limit]
    by_qid = {b["wikidata"]: b for b in targets}
    print(f"QID 를 가진 브랜드 {len(targets):,}개")

    found: dict[str, list[str]] = {}
    qids = list(by_qid)
    for i in range(0, len(qids), CHUNK):
        part = qids[i:i + CHUNK]
        for row in sparql(part):
            qid = row["item"]["value"].rsplit("/", 1)[-1]
            found.setdefault(qid, []).append(row["alias"]["value"])
        print(f"  {min(i + CHUNK, len(qids))}/{len(qids)} 조회")
        time.sleep(2)

    added = 0
    changed = []
    for qid, aliases in found.items():
        b = by_qid[qid]
        # 짧은 표기가 실제로 사람들이 치는 이름이다 (KKR ← Kohlberg Kravis Roberts)
        new = sorted({a for a in aliases if useful(a, b)}, key=len)[:5]
        if not new:
            continue
        changed.append((b["id"], b.get("name_ko") or b.get("name_en"), new))
        added += len(new)
        if not args.dry_run:
            b["aliases"] = (b.get("aliases") or []) + new

    if not args.dry_run:
        BRANDS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")

    print(f"\n{'[dry-run] ' if args.dry_run else ''}별칭 추가 {added}개 / 브랜드 {len(changed)}개")
    for bid, name, new in changed[:15]:
        print(f"  {(name or bid)[:24]:26} + {new}")
    if len(changed) > 15:
        print(f"  … 외 {len(changed)-15}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
