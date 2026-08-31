#!/usr/bin/env python3
"""국내 로고 2차 수집 — 1차에서 'no_logo' 로 빠진 곳을 다른 경로로 뒤진다.

1차(collect-krx.py·collect-kr-institutions.py)는 <img src="...logo...">만 봤다.
그래서 상장사 1,352곳·기관 527곳이 no_logo 로 남았다. 요즘 사이트는 로고를
그렇게만 넣지 않는다:
  · 헤더에 <svg> 를 직접 박아둔다 (파일이 아예 없다)
  · CSS background-image: url(...) 로 넣는다
  · apple-touch-icon 이 180px 이상이라 쓸 만하다
  · 파일명이 'logo' 가 아니다 (ci.png · brand.svg · header_img.png)

⚠️ brands.json 을 직접 쓰지 않는다. 파생물 생성(build-variants·scan-light-logos)
   이 같은 파일을 쓰기 때문에 동시에 돌리면 한쪽 결과가 통째로 날아간다.
   결과는 스테이징 JSON 에 쌓고 --merge 로 나중에 합친다.

  python3 scripts/collect-kr-pass2.py --workers 10        # 수집 → 스테이징
  python3 scripts/collect-kr-pass2.py --merge             # brands.json 에 합치기
"""
import concurrent.futures as cf
import html as htmlmod
import json
import re
import shutil
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_krx_lib import get, ink_ratio, pick_logo, _decode   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
STAGE = ROOT / "_staging-pass2.json"
SNS = re.compile(r"(?<![a-z])(facebook|twitter|youtube|instagram|kakao|naver|linkedin|"
                 r"tiktok|threads|pinterest|telegram|rss|sns|blog|share)(?![a-z])", re.I)


def candidates(h, base):
    """1차보다 넓게 훑는다. 우선순위대로."""
    out = []

    # ① 헤더에 직접 박힌 <svg> — 파일이 없으니 1차가 절대 못 찾는다
    head = h[:40000]
    for m in re.finditer(r"<svg[^>]*>.*?</svg>", head, re.S | re.I):
        blob = m.group(0)
        if len(blob) < 400 or blob.count("<path") + blob.count("<polygon") < 1:
            continue
        # ⚠️ 헤더의 인라인 SVG 는 로고만 있는 게 아니다. 언어선택 지구본·검색·
        #    햄버거 아이콘이 잔뜩 섞여 있다. 네오뷰에서 실제로 지구본을
        #    로고로 가져왔다. 두 신호로 가른다:
        #      · aria-hidden  → 장식용 아이콘이라고 사이트가 스스로 밝힌 것
        #      · viewBox 가 거의 정사각 + 작다 → 아이콘 (15x15 였다)
        #    진짜 워드마크는 가로가 길다 (레메디 341x45.9 = 7.4:1)
        if re.search(r'aria-hidden=["\']?true', blob, re.I):
            continue
        vb = re.search(r'viewBox=["\']([\d.\s-]+)', blob, re.I)
        if vb:
            try:
                _, _, vw, vh = [float(x) for x in vb.group(1).split()[:4]]
                if vh and vw and max(vw, vh) < 40 and 0.7 < vw / vh < 1.4:
                    continue          # 작은 정사각 = 아이콘
            except Exception:
                pass
        out.append(("inline", blob))
        if len([1 for k, _ in out if k == "inline"]) >= 2:
            break

    # ② CSS background-image
    for m in re.finditer(r"background(?:-image)?\s*:[^;}]*url\(['\"]?([^'\")]+)", h, re.I):
        u = m.group(1)
        if re.search(r"logo|ci[_\-.]|symbol|bi[_\-.]", u, re.I) and not SNS.search(u):
            out.append(("url", urllib.parse.urljoin(base, u)))

    # ③ 파일명이 logo 가 아닌 헤더 이미지 — 'ci' 'brand' 'head' 가 든 것
    for s in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', head, re.I):
        if SNS.search(s):
            continue
        if re.search(r"(?<![a-z])(ci|bi|brand|emblem|mark|head(er)?)(?![a-z])", s, re.I):
            out.append(("url", urllib.parse.urljoin(base, s)))

    # ④ apple-touch-icon — 대개 180px 이상이라 쓸 만하다
    for m in re.finditer(r'<link[^>]+rel=["\'][^"\']*apple-touch-icon[^"\']*["\'][^>]*>', h, re.I):
        hm = re.search(r'href=["\']([^"\']+)', m.group(0), re.I)
        if hm:
            out.append(("url", urllib.parse.urljoin(base, htmlmod.unescape(hm.group(1)))))

    seen, uniq = set(), []
    for kind, v in out:
        k = v[:200]
        if k in seen:
            continue
        seen.add(k)
        uniq.append((kind, v))
    return uniq[:6]


def validate(data, is_svg):
    low = data[:400].lower()
    if b"<!doctype html" in low or (b"<html" in low and not is_svg):
        return False
    if is_svg and (b"<image" in data or b"data:image" in data):
        return False
    if not is_svg and len(data) < 900:
        return False
    r, size, bbox = ink_ratio(data, is_svg)
    if r < 0 or r < 0.002 or r > 0.80:
        return False
    if bbox < 0.05:
        return False
    if not is_svg and min(size) < 64:      # 2차는 파비콘 유입이 많아 기준을 올린다
        return False
    if size[1] and size[0] / size[1] > 9 and r > 0.5:
        return False
    return True


def work(t):
    site = t.get("site") or ""
    if not site:
        return ("no_site", t, None, None)
    u = site if site.startswith("http") else "http://" + site
    try:
        page, _ = get(u)
        h = _decode(page)
    except Exception as e:
        return (f"site_fail:{type(e).__name__}", t, None, None)

    # 1차가 이미 본 경로는 건너뛴다 (같은 걸 또 받아봐야 같은 결과다)
    if pick_logo(h, u):
        pass

    for kind, v in candidates(h, u):
        if kind == "inline":
            blob = v.encode("utf-8")
            if b"xmlns" not in blob[:200]:
                blob = blob.replace(b"<svg", b'<svg xmlns="http://www.w3.org/2000/svg"', 1)
            if validate(blob, True):
                return ("ok_inline", t, blob, "svg")
            continue
        try:
            data, _ = get(v, timeout=15, limit=3_000_000)
        except Exception:
            continue
        is_svg = v.lower().split("?")[0].endswith(".svg") or b"<svg" in data[:400].lower()
        if validate(data, is_svg):
            return ("ok", t, data, "svg" if is_svg else "png")
    return ("no_logo", t, None, None)



def wikidata(qid, timeout=150):
    """한국 소재 {qid} 하위 항목의 한국어 라벨과 공식 홈페이지."""
    q = (f'SELECT ?itemLabel ?site WHERE {{ ?item wdt:P31/wdt:P279* wd:{qid} ; '
         f'wdt:P17 wd:Q884 . OPTIONAL{{?item wdt:P856 ?site}} '
         f'SERVICE wikibase:label{{bd:serviceParam wikibase:language "ko,en".}} }} LIMIT 1500')
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q})
    r = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "VibersLogoCollector/1.0 (https://semologo.com)",
                      "Accept": "application/sparql-results+json"}), timeout=timeout)
    out = {}
    for x in json.loads(r.read())["results"]["bindings"]:
        nm = x["itemLabel"]["value"]
        if re.fullmatch(r"Q\d+", nm):
            continue
        out.setdefault(nm, x.get("site", {}).get("value", ""))
    return out


def load_targets(known, dom):
    """1차에서 못 채운 곳 = 명단에는 있는데 카탈로그에 없는 곳."""
    norm = lambda s: re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())
    out = []
    krx = ROOT / "_targets" / "krx.json"
    if krx.exists():
        for c in json.loads(krx.read_text()):
            d = re.sub(r"^https?://(www\.)?|/.*$", "", c["site"] or "").lower()
            if norm(c["name"]) in known or (d and d in dom):
                continue
            out.append({"name": c["name"], "site": c["site"], "cat": None,
                        "sector": c.get("sector", ""), "kind": "krx"})
    # 공공기관·대학·병원·언론사·구단은 위키데이터에서 직접 받는다.
    # ⚠️ 예전엔 /tmp 의 중간 파일을 읽었다. CI 는 매번 빈 러너라 그 파일이
    #    없고, 조건이 조용히 거짓이 돼 **대상 0건으로 정상 종료**했다.
    #    에러가 안 나서 아무도 모른다.
    for kd, qid, cat in (("gov", "Q327333", "공공·기관"),
                         ("univ", "Q3918", "교육"),
                         ("hosp", "Q16917", "의료·바이오"),
                         ("media", "Q1002697", "미디어·엔터"),
                         ("club", "Q4438121", "스포츠")):
        try:
            rows = wikidata(qid)
        except Exception as e:
            print(f"  ⚠️ {kd} 명단 조회 실패 {type(e).__name__} — 이 분류는 건너뛴다")
            continue
        for nm, site in rows.items():
            d = re.sub(r"^https?://(www\.)?|/.*$", "", site or "").lower()
            if norm(nm) in known or (d and d in dom):
                continue
            out.append({"name": nm, "site": site, "cat": cat, "kind": kd})

    # 지자체 — 이름은 이미 동명 시도 병기까지 끝난 목록을 그대로 쓴다.
    # 여기서 다시 만들면 1차와 이름이 갈라져 같은 구가 두 항목이 된다.
    sg = ROOT / "_targets" / "sgg-targets.json"
    if sg.exists():
        for r in json.loads(sg.read_text()):
            site = r.get("site") or ""
            d = re.sub(r"^https?://(www\.)?|/.*$", "", site).lower()
            if norm(r["name"]) in known or (d and d in dom):
                continue
            out.append({"name": r["name"], "site": site,
                        "cat": "공공·기관", "kind": "muni"})

    return out


def main():
    if "--merge" in sys.argv:
        return merge()
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 10
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

    bl = json.loads((C / "brands.json").read_text())
    bl = bl["brands"] if isinstance(bl, dict) else bl
    norm = lambda s: re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())
    known, dom = set(), set()
    for b in bl:
        for k in (b.get("name_ko"), b.get("name_en"), b["id"], *(b.get("aliases") or [])):
            n = norm(k)
            if n:
                known.add(n)
        d = str(b.get("domain") or "").lower().replace("www.", "")
        if d:
            dom.add(d)

    todo = load_targets(known, dom)
    print(f"2차 대상 {len(todo):,}곳", flush=True)
    if limit:
        todo = todo[:limit]

    stage = json.loads(STAGE.read_text()) if STAGE.exists() else []
    done = {s["site"] for s in stage}
    todo = [t for t in todo if t["site"] not in done]

    ok, stats = 0, {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for n, (st, t, blob, ext) in enumerate(ex.map(work, todo), 1):
            stats[st.split(":")[0]] = stats.get(st.split(":")[0], 0) + 1
            if not st.startswith("ok"):
                continue
            stage.append({"name": t["name"], "site": t["site"], "cat": t.get("cat"),
                          "sector": t.get("sector", ""), "kind": t["kind"],
                          "ext": ext, "how": st,
                          "data": blob.decode("utf-8", "ignore") if ext == "svg"
                                  else __import__("base64").b64encode(blob).decode()})
            ok += 1
            if n % 100 == 0:
                print(f"  {n}/{len(todo)} · 수집 {ok}", flush=True)
                STAGE.write_text(json.dumps(stage, ensure_ascii=False))
    STAGE.write_text(json.dumps(stage, ensure_ascii=False))
    print(f"\n✅ 2차 {ok}건 스테이징 (누적 {len(stage)})")
    print("   내역: " + " · ".join(f"{k} {v}" for k, v in sorted(stats.items())))
    print(f"   합치기: python3 {Path(__file__).name} --merge")
    return 0


def merge():
    import base64
    if not STAGE.exists():
        print("스테이징 파일이 없다")
        return 1
    stage = json.loads(STAGE.read_text())
    data = json.loads((C / "brands.json").read_text())
    bl = data["brands"] if isinstance(data, dict) else data
    ids = {b["id"] for b in bl}
    norm = lambda s: re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())
    known = {norm(b.get("name_ko")) for b in bl} | {norm(b["id"]) for b in bl}
    SEC = None
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("ckrx", ROOT / "scripts" / "collect-krx.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        SEC = m.category
    except Exception:
        pass

    added = 0
    for s in stage:
        if norm(s["name"]) in known:
            continue
        d = re.sub(r"^https?://(www\.)?|/.*$", "", s["site"] or "").lower()
        base = re.sub(r"\.(go|ac|or|re|co)?\.?kr$|\.(com|net|org)$", "", d)
        base = re.sub(r"[^a-z0-9]", "", base) or ("kr" + str(added))
        bid, n = base, 2
        while bid in ids:
            bid = f"{base}-{n}"
            n += 1
        blob = (s["data"].encode("utf-8") if s["ext"] == "svg"
                else base64.b64decode(s["data"]))
        p = C / bid
        p.mkdir(parents=True, exist_ok=True)
        is_svg = s["ext"] == "svg"
        (p / ("logo.svg" if is_svg else "logo.png")).write_bytes(blob)
        if is_svg:
            try:
                import cairosvg
                cairosvg.svg2png(bytestring=blob, write_to=str(p / "logo.png"), output_width=800)
            except Exception as e:
                print(f"  ❌ {bid}: PNG 변환 실패 {type(e).__name__} — 등록 안 함")
                shutil.rmtree(p, ignore_errors=True)
                continue
        cat = s.get("cat") or (SEC(s.get("sector", "")) if SEC else "기타")
        bl.append({
            "id": bid, "name_ko": s["name"], "name_en": s["name"], "category": cat,
            "folder": f"_clients/{bid}", "website": s["site"], "domain": d,
            "logo_svg": "logo.svg" if is_svg else None, "has_svg": is_svg,
            "logo_png": True, "has_png": True,
            "svg_source": f"kr-{s['kind']}-pass2", "added_at": time.strftime("%Y-%m-%d"),
            "sources": [{"provider": f"kr-{s['kind']}-pass2",
                         "file": "logo.svg" if is_svg else "logo.png",
                         "origin": s["site"], "how": s.get("how")}],
        })
        ids.add(bid)
        known.add(norm(s["name"]))
        added += 1
    (C / "brands.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"✅ 합침 {added}건 (총 {len(bl):,}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
