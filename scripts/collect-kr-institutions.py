#!/usr/bin/env python3
"""국내 공공기관·대학·병원 로고를 각 기관 홈페이지에서 수집한다.

collect-krx.py 와 같은 방식이고 **명단 출처만 다르다**. 상장사는 KRX 목록이
있지만 기관·대학·병원은 그런 다운로드가 없어 위키데이터에서 뽑는다.

2026-08-29 실측 보유율 — 국내가 거의 비어 있었다:
  공공기관  972개 중 121 (12%)
  대학      398개 중  19 ( 5%)
  병원      352개 중   6 ( 2%)

검사는 collect-krx.py 와 동일하다(그쪽에서 실제로 뚫린 것들을 반영했다):
  · 404 HTML 이 이미지로 오는 것
  · 비트맵을 감싼 SVG
  · 흰색 전용(잉크 0%) — 카드에서 빈칸이 된다
  · 잉크 80% 초과 — 배경이 칠해진 배너다(매드업 사례)
  · **내용 경계상자 5% 미만** — 캔버스 구석의 점. 잉크 검사를 통과해버린다
    (애경산업은 og:image 홍보 이미지가 잡혔었다)
  · PNG 변환 실패 시 등록하지 않는다 — has_png=true 인데 파일이 없으면 404

  python3 scripts/collect-kr-institutions.py --kind gov --dry-run
  python3 scripts/collect-kr-institutions.py --kind univ --limit 30
  python3 scripts/collect-kr-institutions.py --kind all --workers 10
"""
import concurrent.futures as cf
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_krx_lib import get, ink_ratio, pick_logo, UA   # noqa: E402  (아래에서 생성)

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
SPARQL = "https://query.wikidata.org/sparql"

KINDS = {
    "gov":  ("Q327333", "공공·기관",   "공공기관"),
    "univ": ("Q3918",   "교육",        "대학"),
    "hosp": ("Q16917",  "의료·바이오",  "병원"),
}


def fetch_list(kind):
    qid, _, _ = KINDS[kind]
    q = (f'SELECT ?item ?itemLabel ?site WHERE {{ '
         f'?item wdt:P31/wdt:P279* wd:{qid} ; wdt:P17 wd:Q884 . '
         f'OPTIONAL{{?item wdt:P856 ?site}} '
         f'SERVICE wikibase:label{{bd:serviceParam wikibase:language "ko,en".}} }} LIMIT 1500')
    url = SPARQL + "?" + urllib.parse.urlencode({"query": q})
    r = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "VibersLogoCollector/1.0 (https://semologo.com)",
                      "Accept": "application/sparql-results+json"}), timeout=120)
    rows = json.loads(r.read())["results"]["bindings"]
    seen = {}
    for x in rows:
        nm = x["itemLabel"]["value"]
        if re.fullmatch(r"Q\d+", nm):      # 라벨이 없는 항목은 쓸 수 없다
            continue
        seen.setdefault(nm, x.get("site", {}).get("value", ""))
    return [{"name": n, "site": s} for n, s in seen.items()]


def work(inst):
    site = inst["site"]
    if not site:
        return ("no_site", inst, None, None)
    u = site if site.startswith("http") else "http://" + site
    try:
        page, _ = get(u)
        h = page.decode("utf-8", "ignore")
    except Exception as e:
        return (f"site_fail:{type(e).__name__}", inst, None, None)

    for cand in pick_logo(h, u):
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
        if 0 <= r < 0.002 or r > 0.80:
            continue
        if 0 <= bbox < 0.05:
            continue
        if not is_svg and min(size) < 40:
            continue
        if size[1] and size[0] / size[1] > 9 and r > 0.5:
            continue
        return ("ok", inst, data,
                "svg" if is_svg else (cand.lower().split("?")[0].rsplit(".", 1)[-1][:4] or "png"))
    return ("no_logo", inst, None, None)


def make_id(inst, taken, kind):
    d = re.sub(r"^https?://(www\.)?|/.*$", "", inst["site"] or "").lower()
    base = re.sub(r"\.(go\.kr|ac\.kr|or\.kr|re\.kr|co\.kr|kr|com|net|org)$", "", d)
    base = re.sub(r"[^a-z0-9]", "", base)
    if not base or len(base) < 2:
        base = kind + re.sub(r"[^a-z0-9]", "", inst["name"].lower())[:12]
    bid, n = base, 2
    while bid in taken:
        bid = f"{base}-{n}"
        n += 1
    return bid


def main():
    dry = "--dry-run" in sys.argv
    kind = sys.argv[sys.argv.index("--kind") + 1] if "--kind" in sys.argv else "all"
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 10
    kinds = list(KINDS) if kind == "all" else [kind]

    data = json.loads((C / "brands.json").read_text())
    bl = data["brands"] if isinstance(data, dict) else data
    norm = lambda s: re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())
    known, dom, ids = set(), set(), set()
    for b in bl:
        ids.add(b["id"])
        for k in (b.get("name_ko"), b.get("name_en"), b["id"], *(b.get("aliases") or [])):
            n = norm(k)
            if n:
                known.add(n)
        d = str(b.get("domain") or "").lower().replace("www.", "")
        if d:
            dom.add(d)

    grand = 0
    for kd in kinds:
        _, cat, label = KINDS[kd]
        lst = fetch_list(kd)
        todo = []
        for c in lst:
            d = re.sub(r"^https?://(www\.)?|/.*$", "", c["site"] or "").lower()
            if norm(c["name"]) in known or (d and d in dom):
                continue
            todo.append(c)
        print(f"\n[{label}] 총 {len(lst):,} · 미보유 {len(todo):,}", flush=True)
        if limit:
            todo = todo[:limit]
        if dry:
            for c in todo[:15]:
                print(f"   {c['name'][:24]:<26} {c['site'][:44]}")
            continue

        ok, stats, added = 0, {}, []
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for n, (st, inst, blob, ext) in enumerate(ex.map(work, todo), 1):
                stats[st.split(":")[0]] = stats.get(st.split(":")[0], 0) + 1
                if st != "ok":
                    continue
                bid = make_id(inst, ids, kd)
                ids.add(bid)
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
                added.append({
                    "id": bid, "name_ko": inst["name"], "name_en": inst["name"],
                    "category": cat, "folder": f"_clients/{bid}",
                    "website": inst["site"],
                    "domain": re.sub(r"^https?://(www\.)?|/.*$", "", inst["site"] or "").lower(),
                    "logo_svg": "logo.svg" if is_svg else None, "has_svg": is_svg,
                    "logo_png": True, "has_png": True,
                    "svg_source": f"kr-{kd}-site", "kr_kind": label,
                    "added_at": time.strftime("%Y-%m-%d"),
                    "sources": [{"provider": f"kr-{kd}-site",
                                 "file": "logo.svg" if is_svg else "logo.png",
                                 "origin": inst["site"]}],
                })
                ok += 1
                if n % 50 == 0:
                    print(f"   {n}/{len(todo)} · 수집 {ok}", flush=True)
        bl.extend(added)
        grand += ok
        print(f"   ✅ {label} {ok}건 — " + " · ".join(f"{k} {v}" for k, v in sorted(stats.items())))

    if grand and not dry:
        (C / "brands.json").write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        print(f"\n✅ 합계 {grand}건 (총 {len(bl):,}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
