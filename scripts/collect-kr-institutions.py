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
from collect_krx_lib import get, ink_ratio, pick_logo, _decode   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
SPARQL = "https://query.wikidata.org/sparql"

KINDS = {
    "gov":  ("Q327333",  "공공·기관",   "공공기관"),
    "univ": ("Q3918",    "교육",        "대학"),
    "hosp": ("Q16917",   "의료·바이오",  "병원"),
    # 2026-08-29 추가. 보유율이 각각 6%·4% 였다
    "media": ("Q1002697", "미디어·엔터", "언론사"),
    "club":  ("Q4438121", "스포츠",      "스포츠구단"),
}

# 위키데이터로 못 뽑는 명단은 파일에서 읽는다.
# 지자체는 위키데이터 P31 분류가 제각각이라(시·군·구가 서로 다른 타입) 쿼리로
# 한 번에 못 모은다. 위키백과 '대한민국의 행정 구역' 링크에서 263개를 뽑고
# 홈페이지만 위키데이터 P856 으로 채웠다.
FILE_KINDS = {
    "muni": ("_targets/sgg-targets.json", "공공·기관", "지자체"),
}


def fetch_list(kind):
    if kind in FILE_KINDS:
        path, _, _ = FILE_KINDS[kind]
        rows = json.loads((ROOT / path).read_text())
        return [{"name": r["name"], "site": r.get("site", "")} for r in rows]
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
        h = _decode(page)
    except Exception as e:
        return (f"site_fail:{type(e).__name__}", inst, None, None)

    # 지자체는 **심볼 CI 와 브랜드 슬로건을 따로** 운영하는 곳이 많다.
    # (예: 광진구의 심볼 마크와 'A+ 광진' 슬로건). 둘은 같은 브랜드의 다른
    # 형태이므로 항목을 쪼개지 않고 한 브랜드의 변형 2종으로 담는다.
    # 그래서 첫 통과분에서 멈추지 않고 최대 2개까지 모은다.
    found = []
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
        if r < 0 or r < 0.002 or r > 0.80:   # r<0 은 렌더 실패·문장 이미지
            continue
        if bbox < 0.05:
            continue
        if not is_svg and min(size) < 40:
            continue
        if size[1] and size[0] / size[1] > 9 and r > 0.5:
            continue
        ext = "svg" if is_svg else (cand.lower().split("?")[0].rsplit(".", 1)[-1][:4] or "png")
        # 같은 그림을 두 번 담지 않는다 — 종횡비가 비슷하면 같은 것으로 본다
        ar = size[0] / max(1, size[1])
        if any(abs(ar - a) < 0.35 for _, _, a in found):
            continue
        found.append((data, ext, ar))
        if len(found) >= 2:
            break
    if found:
        return ("ok", inst, found, None)
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
    kinds = list(KINDS) + list(FILE_KINDS) if kind == "all" else [kind]

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
        _, cat, label = (FILE_KINDS[kd] if kd in FILE_KINDS else KINDS[kd])[-3:] \
            if kd in FILE_KINDS else KINDS[kd]
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
            for n, (st, inst, payload, _unused) in enumerate(ex.map(work, todo), 1):
                stats[st.split(":")[0]] = stats.get(st.split(":")[0], 0) + 1
                if st != "ok":
                    continue
                # payload 는 [(데이터, 확장자, 종횡비), ...] — 최대 2종
                blob, ext, _ = payload[0]
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
                # 두 번째 형태(대개 브랜드 슬로건)는 variants/ 에 둔다.
                # build-logo-variants.py 가 variants.override.json 을 존중하므로
                # 여기서 만든 것이 나중 실행에 덮이지 않는다.
                if len(payload) > 1:
                    b2, e2, _ = payload[1]
                    vd = d / "variants"
                    vd.mkdir(exist_ok=True)
                    name = "slogan.svg" if e2 == "svg" else "slogan.png"
                    (vd / name).write_bytes(b2)
                    if e2 == "svg":
                        try:
                            import cairosvg
                            cairosvg.svg2png(bytestring=b2,
                                             write_to=str(vd / "slogan.png"), output_width=800)
                        except Exception:
                            pass
                    (d / "variants.override.json").write_text(json.dumps({
                        "schema": 1, "origin": "manual", "id": bid,
                        "variants": [
                            {"key": "primary", "form": "unknown", "label": "심볼·기본형",
                             "files": {("svg" if is_svg else "png"):
                                       ("logo.svg" if is_svg else "logo.png")}},
                            {"key": "slogan", "form": "wordmark", "label": "브랜드 슬로건",
                             "files": {("svg" if e2 == "svg" else "png"): f"variants/{name}"}},
                        ],
                    }, ensure_ascii=False, indent=1))
                    stats["slogan"] = stats.get("slogan", 0) + 1
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
