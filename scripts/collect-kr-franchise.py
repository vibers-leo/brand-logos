#!/usr/bin/env python3
"""국내 프랜차이즈 로고 수집 — ⚠️ 현재 **사용하지 말 것**. 정확도 미달.

명단(_targets/franchise.json, 11,846건)은 공정거래위원회 가맹사업
정보공개서에서 받아 확보돼 있다. 미보유가 99.6%라 가치는 크다.
문제는 **로고를 어디서 받느냐**다.

■ 세 번 시도해서 세 번 다 실패했다 (2026-08-29)
  ① 검색 1위 사용        → 10건 전부 가짜
     changupdo.com(창업도)·shinailbo.co.kr(신아일보)·fran114.com·fchamall.com
  ② 도메인 반복 4회 이상  → 2건 여전히 가짜
     yoda.wiki(위키)·ikfa.or.kr(한국프랜차이즈산업협회)도 4회씩 반복된다
  ③ 제목에 브랜드명 대조  → 신호가 안 나온다
     커피니→'COFFEENIE' · 이디야커피→'EDIYA COFFEE' · 한솔노피곰→'노피곰'
     한글 브랜드명이 사이트 제목에 그대로 있는 경우가 사실상 없다

■ 근본 원인
프랜차이즈 검색 결과는 창업 중개 생태계가 뒤덮고 있다. 이 분야의 구조라
차단 목록을 늘리는 걸로는 못 이긴다 — 두더지잡기가 된다.

■ 다시 하려면
  · 공정위 상세 페이지(encFirMstSn)에 접근하는 방법을 찾는다.
    정보공개서 원문에 홈페이지가 있을 수 있다. 지금은 세션 문제로 막혔다
  · 또는 사람이 상위 브랜드 수백 개만 확인해 준다. 검색량이 거기 몰린다
  · 자동 판정이 확실해지기 전에는 돌리지 않는다. 가짜가 들어가면
    '형지글로벌에 인스타그램 로고' 같은 사고가 대량으로 난다

  python3 scripts/collect-kr-franchise.py --dry-run   # 대상만 확인
"""
import concurrent.futures as cf
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_krx_lib import get, ink_ratio, pick_logo   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
TARGETS = ROOT / "_targets" / "franchise.json"
HUB = "https://naverapihub.apigw.ntruss.com/search/v1/webkr"

# 공식 사이트가 아닌 곳 — 창업정보 중개·위키·블로그·쇼핑몰
BLOCK = re.compile(
    r"(jumpo\.shop|startuplus\.kr|fchalab\.com|hi-franchise\.com|franchise\.ftc\.go\.kr|"
    r"namu\.wiki|wikipedia|blog\.|tistory\.com|brunch\.co\.kr|cafe\.naver|"
    r"post\.naver|m\.blog|youtube\.com|instagram\.com|facebook\.com|"
    r"news\.|magazine\.|thevc\.kr|jobkorea|saramin|catch\.co\.kr|"
    r"smartstore\.naver|coupang\.com|11st\.co\.kr|gmarket)", re.I)


def hub_search(q, n=5):
    id_, sec = os.environ.get("NAVER_APIHUB_CLIENT_ID"), os.environ.get("NAVER_APIHUB_CLIENT_SECRET")
    if not id_ or not sec:
        raise SystemExit("NAVER_APIHUB_CLIENT_ID / SECRET 이 없다 — .secrets 를 source 할 것")
    u = f"{HUB}?query={urllib.parse.quote(q)}&display={n}"
    r = urllib.request.urlopen(urllib.request.Request(
        u, headers={"X-NCP-APIGW-API-KEY-ID": id_, "X-NCP-APIGW-API-KEY": sec}), timeout=20)
    return json.loads(r.read()).get("items", [])


MIN_HITS = 4          # 검색 10건 중 이만큼 반복돼야 공식으로 본다


def official_site(brand, hq):
    """브랜드의 공식 사이트를 고른다. 못 고르면 None.

    ⚠️ 검색 1위를 그대로 쓰면 안 된다. 창업정보 중개(changupdo·jumpo.shop·
       fran114)·언론사(shinailbo)가 상위를 차지한다. 실제로 그렇게 10건을
       수집했다가 전부 되돌렸다 — 브랜드 사이트가 하나도 없었다.

       차단 목록을 늘리는 건 두더지잡기다. 대신 **도메인 반복 횟수**를 본다.
       자체 홈페이지가 있는 브랜드는 검색 결과가 그 도메인으로 쏠린다:
         커피니 coffeenie.co.kr 8/10 · 이디야 ediya.com 7/10 · 노피곰 4/10
       자체 사이트가 없으면 최다 도메인이 2회를 못 넘는다:
         브레인스쿨 2 · 타카 2 · 오적회관 1
       그런 브랜드는 수집 대상이 아니다 — 건너뛰는 게 맞다.
    """
    from collections import Counter
    try:
        items = hub_search(f"{brand} 프랜차이즈 가맹", 10)
    except Exception:
        return None
    hosts = Counter()
    for it in items:
        link = it.get("link") or ""
        if BLOCK.search(link):
            continue
        host = re.sub(r"^https?://(www\.)?|/.*$", "", link).lower()
        if host and host.count(".") >= 1:
            hosts[host] += 1
    if not hosts:
        return None
    host, n = hosts.most_common(1)[0]
    if n < MIN_HITS:
        return None
    return f"https://{host}"


def work(row):
    brand = row["brand"]
    site = official_site(brand, row.get("hq"))
    if not site:
        return ("no_site", row, None, None)
    try:
        page, _ = get(site)
        h = page.decode("utf-8", "ignore")
    except Exception as e:
        return (f"site_fail:{type(e).__name__}", row, None, None)

    for cand in pick_logo(h, site):
        try:
            data, _ = get(cand, timeout=15, limit=3_000_000)
        except Exception:
            continue
        low = data[:400].lower()
        if b"<!doctype html" in low or b"<html" in low:
            continue
        is_svg = cand.lower().split("?")[0].endswith(".svg") or b"<svg" in low
        if is_svg and (b"<image" in data or b"data:image" in data):
            continue
        if not is_svg and len(data) < 900:
            continue
        r, size, bbox = ink_ratio(data, is_svg)
        if r < 0 or r < 0.002 or r > 0.80 or bbox < 0.05:
            continue
        if not is_svg and min(size) < 40:
            continue
        if size[1] and size[0] / size[1] > 9 and r > 0.5:
            continue
        return ("ok", dict(row, site=site), data, "svg" if is_svg else "png")
    return ("no_logo", dict(row, site=site), None, None)


def main():
    dry = "--dry-run" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 6

    rows = json.loads(TARGETS.read_text())
    data = json.loads((C / "brands.json").read_text())
    bl = data["brands"] if isinstance(data, dict) else data
    norm = lambda s: re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())
    known, ids = set(), {b["id"] for b in bl}
    for b in bl:
        for k in (b.get("name_ko"), b.get("name_en"), b["id"], *(b.get("aliases") or [])):
            n = norm(k)
            if n:
                known.add(n)
    dead = set()
    tomb = C / "_deleted.json"
    if tomb.exists():
        dead = set(json.loads(tomb.read_text()))

    todo = [r for r in rows if norm(r["brand"]) not in known]
    print(f"프랜차이즈 {len(rows):,} · 미보유 {len(todo):,}", flush=True)
    if limit:
        todo = todo[:limit]
    if dry:
        for r in todo[:15]:
            print(f"  {r['brand'][:24]:<26} {r['hq'][:22]}")
        return 0

    ok, stats, added = 0, {}, []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for n, (st, row, blob, ext) in enumerate(ex.map(work, todo), 1):
            stats[st.split(":")[0]] = stats.get(st.split(":")[0], 0) + 1
            if st != "ok":
                continue
            host = re.sub(r"^https?://(www\.)?|/.*$", "", row["site"]).lower()
            base = re.sub(r"\.(co\.kr|or\.kr|kr|com|net|shop)$", "", host)
            base = re.sub(r"[^a-z0-9]", "", base) or f"fc{row['no']}"
            bid, k = base, 2
            while bid in ids or bid in dead:
                bid = f"{base}-{k}"
                k += 1
            d = C / bid
            d.mkdir(parents=True, exist_ok=True)
            is_svg = ext == "svg"
            (d / ("logo.svg" if is_svg else "logo.png")).write_bytes(blob)
            if is_svg:
                try:
                    import cairosvg
                    cairosvg.svg2png(bytestring=blob, write_to=str(d / "logo.png"),
                                     output_width=800)
                except Exception as e:
                    print(f"  ❌ {bid}: PNG 변환 실패 {type(e).__name__} — 등록 안 함")
                    stats["png_fail"] = stats.get("png_fail", 0) + 1
                    shutil.rmtree(d, ignore_errors=True)
                    continue
            ids.add(bid)
            added.append({
                "id": bid, "name_ko": row["brand"], "name_en": row["brand"],
                "category": "유통·쇼핑", "folder": f"_clients/{bid}",
                "website": row["site"], "domain": host,
                "logo_svg": "logo.svg" if is_svg else None, "has_svg": is_svg,
                "logo_png": True, "has_png": True,
                "svg_source": "kr-franchise", "kr_kind": "프랜차이즈",
                "franchise_hq": row.get("hq"), "franchise_reg": row.get("reg"),
                "added_at": time.strftime("%Y-%m-%d"),
                "sources": [{"provider": "kr-franchise",
                             "file": "logo.svg" if is_svg else "logo.png",
                             "origin": row["site"]}],
            })
            ok += 1
            if n % 50 == 0:
                print(f"  {n}/{len(todo)} · 수집 {ok}", flush=True)

    if added:
        bl.extend(added)
        (C / "brands.json").write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"\n✅ 프랜차이즈 {ok}건 (총 {len(bl):,}개)")
    print("   내역: " + " · ".join(f"{k} {v}" for k, v in sorted(stats.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
