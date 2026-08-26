#!/usr/bin/env python3
"""
심볼만 있는 브랜드에 위키미디어 커먼즈의 워드마크 판을 채운다.

왜 이 소스인가 —
카탈로그 기반 소스(svgl·VLZ·gilbarbara)는 수백 건 규모에서 고갈됐다.
커먼즈는 이미 우리 최대 소스(33,819건)지만 **워드마크는 따로 안 가져왔다.**
심볼만 있는 7,690개를 이름으로 되짚어 워드마크 파일을 찾는다.
실측 수율 8% → 약 576건.

⚠️ 자유 검색 1등을 그대로 믿으면 안 된다. 실측한 오답들:
     NASA        → 미국 NASA '깃발'
     국제사법재판소 → 니카라과-콜롬비아 '해양경계 지도'
     Yale University → Yale University '출판부' 로고
   그래서 가드 3중을 건다:
     ① 파일명에 wordmark/logotype 이 들어갈 것 (검색 매칭만으론 부족)
     ② 브랜드명이 파일명에 그대로 들어갈 것 (정규화 후 부분일치)
     ③ 받은 뒤 종횡비가 기존 심볼과 0.4 이상 벌어질 것
   ①②만으로 40건 중 37건이 걸러졌다. 느슨하게 풀지 마라.

⚠️ 파일만 받으면 반영되지 않는다. build-logo-variants.py 는 디스크가 아니라
   brands.json 의 sources[] 를 읽는다.

  python3 scripts/collect-wordmarks-commons.py --dry-run --limit 40
  python3 scripts/collect-wordmarks-commons.py --limit 50
  python3 scripts/collect-wordmarks-commons.py
"""
import hashlib, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
API = "https://commons.wikimedia.org/w/api.php"
UA = "VibersLogoCollector/1.0 (https://semologo.com)"
WM = re.compile(r"wordmark|logotype|word[ _-]mark", re.I)
# 파일명 끝의 언어코드 (Wiktionary-wordmark-sh.svg 등)
LANG = re.compile(r"[-_]([a-z]{2,3})([-_][a-z]{2,4})?\.svg$", re.I)
# 브랜드명이 들어있어도 다른 조직·제품인 경우가 있다. 실측된 오답:
#   OpenStreetMap → "OpenStreetMap Wiki wordmark proposal"
#   Roblox        → "Roblox Studio wordmark" (다른 제품)
#   Burton        → "Burton Blatt Institute Syracuse University" (완전 다른 조직)
SUB = re.compile(r"\b(wiki|press|foundation|museum|records|studios?|network|channel|"
                 r"magazine|award|festival|college|school|institute|library|"
                 r"conference|summit|proposal|draft|concept)\b", re.I)

def get(url, timeout=30):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout).read()

def aspect(path_or_bytes):
    b = path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()
    m = re.search(rb'viewBox="([\d.\s-]+)"', b)
    if not m:
        return None
    v = m.group(1).split()
    if len(v) != 4:
        return None
    try:
        w, h = float(v[2]), float(v[3])
        return round(w / h, 2) if h > 0 else None
    except ValueError:
        return None

def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())

def commons_url(fname):
    """커먼즈 원본 URL 은 MD5 앞 2자로 갈라진 경로다."""
    f = fname.replace(" ", "_")
    h = hashlib.md5(f.encode("utf-8")).hexdigest()
    return f"https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[:2]}/{urllib.parse.quote(f)}"

def search(name):
    q = f'intitle:"{name}" (wordmark OR logotype) filetype:drawing'
    u = API + "?" + urllib.parse.urlencode({
        "action": "query", "list": "search", "srsearch": q,
        "srnamespace": 6, "srlimit": 5, "format": "json"})
    r = json.loads(get(u, timeout=25))
    return [s["title"][5:] for s in r.get("query", {}).get("search", [])
            if s["title"].lower().endswith(".svg")]

def main():
    dry = "--dry-run" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

    idx = json.load(open(C / "variants-index.json"))["brands"]
    slim = json.load(open(C / "brands-slim.json"))
    slim = slim["brands"] if isinstance(slim, dict) else slim
    m = {x["id"]: x for x in slim}

    cands = []
    for bid, v in idx.items():
        if tuple(sorted(v.get("forms") or [])) != ("symbol",):
            continue
        x = m.get(bid)
        if not x:
            continue
        d = C / bid / "sources"
        # 다른 소스로 이미 채운 브랜드는 건너뛴다
        if any((d / a / b).exists() for a, b in
               [("vlz", "wide.svg"), ("thesvg", "wordmark.svg"),
                ("gilbarbara", "full.svg"), ("svgl", "wordmark.svg"),
                ("commons-wm", "wordmark.svg")]):
            continue
        n = (x.get("name_en") or "").strip()
        if len(n) > 3:
            cands.append((bid, n, x.get("fame") or 0))
    # 인지도 높은 것부터 — 중간에 멈춰도 값이 큰 것부터 채워진다
    cands.sort(key=lambda t: -t[2])
    if limit:
        cands = cands[:limit]

    print(f"대상 {len(cands):,}개 (심볼만 + 영문명 보유, 인지도순)", flush=True)

    ok = fail = skip = nomatch = 0
    picked = []
    for i, (bid, name, _f) in enumerate(cands, 1):
        try:
            files = search(name)
        except Exception as e:
            fail += 1
            files = []
        nb = norm(name)
        good = [f for f in files if WM.search(f) and nb and nb in norm(f)]
        # 언어판을 걸러낸다. 'Wiktionary-wordmark-sh.svg' 는 세르보크로아트어판이라
        # 렌더하면 'Wikirječnik' 이 나온다 — 파일명 가드는 통과하지만 오답이다.
        good = [f for f in good if not LANG.search(f)]
        # 브랜드명을 뺀 나머지에 하위 브랜드·다른 조직 낱말이 있으면 버린다
        good = [f for f in good if not SUB.search(re.sub(re.escape(name), "", f, flags=re.I))]
        # 남은 것 중 군더더기가 가장 적은 것을 고른다. 'Wikimania Nairobi wordmark'
        # 처럼 특정 회차·지부판보다 일반 워드마크가 짧다.
        good.sort(key=lambda f: len(norm(f)))
        if not good:
            nomatch += 1
        else:
            picked.append((bid, name, good[0]))
        if i % 200 == 0:
            print(f"  {i}/{len(cands)} · 후보 {len(picked)}", flush=True)
        time.sleep(0.3)

    print(f"\n가드 통과 {len(picked)}건 / 조회 {len(cands)}건", flush=True)
    if dry:
        for bid, name, f in picked[:20]:
            print(f"  {bid:<26} ← {f}")
        return 0

    for bid, name, fname in picked:
        out = C / bid / "sources" / "commons-wm" / "wordmark.svg"
        try:
            # ⚠️ upload.wikimedia.org 는 연속 다운로드를 막는다. 0.15초 간격으로
            #    돌렸다가 201건 중 177건이 전멸했다(2026-08-26). URL 은 멀쩡했고
            #    나중에 하나씩 받으니 전부 200 이었다 — 순수한 속도 문제다.
            #    간격 0.8초 + 지수 백오프 3회로 해결된다.
            data = None
            for attempt in range(3):
                try:
                    data = get(commons_url(fname), timeout=30)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2 * (attempt + 1))
            if not data or b"<svg" not in data[:400].lower():
                raise ValueError("SVG 아님")
            cur, new_ar = aspect(C / bid / "logo.svg"), aspect(data)
            if cur and new_ar and abs(new_ar - cur) < 0.4:
                skip += 1
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ❌ {bid} ← {fname}: {type(e).__name__}")
        time.sleep(0.8)

    # sources[] 등록 — 이걸 빠뜨리면 파일만 쌓이고 사이트에 안 나온다
    bp = C / "brands.json"
    data = json.load(open(bp))
    bl = data["brands"] if isinstance(data, dict) else data
    bm = {b["id"]: b for b in bl}
    reg = 0
    for bid, name, fname in picked:
        if not (C / bid / "sources" / "commons-wm" / "wordmark.svg").exists():
            continue
        b = bm.get(bid)
        if not b:
            continue
        rel = "sources/commons-wm/wordmark.svg"
        srcs = b.setdefault("sources", [])
        if any(s.get("file") == rel for s in srcs):
            continue
        srcs.append({"provider": "wikimedia", "file": rel, "label": "워드마크",
                     "origin_file": fname})
        reg += 1
    bp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))

    print(f"\n✅ 수집 {ok}건 · 등록 {reg}건 · 중복 {skip}건 · 매칭없음 {nomatch}건 · 실패 {fail}건")
    print("   다음: build-logo-variants.py → build-slim.py → sync-all-bucket.py")
    return 0

if __name__ == "__main__":
    sys.exit(main())
