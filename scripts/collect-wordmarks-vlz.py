#!/usr/bin/env python3
"""
심볼만 있는 브랜드에 VectorLogoZone 의 가로형(ar21) 로고를 채운다.

왜 이 소스인가 —
VLZ 는 슬러그마다 `-ar21`(가로 2:1, 대개 심볼+글자)과 `-icon`(심볼)을
쌍으로 갖고 있다. 형태 규칙이 파일명에 박혀 있어 매칭이 확실하다.
심볼-only 브랜드 8,480개 중 349건이 겹친다(theSVG 181건보다 많다).

경로: src/content/logos/{slug}/{slug}-ar21.svg   ← logos/ 가 아니다

⚠️ 매칭 시 3자 미만 키는 버린다. 한글 브랜드명을 정규화하면 빈 문자열이
   되는데 그걸 키로 쓰면 서로 다른 브랜드가 한 슬러그로 뭉친다.

⚠️ 파일만 받아두면 반영되지 않는다. build-logo-variants.py 는 디스크가
   아니라 brands.json 의 sources[] 를 읽는다 — 등록까지 해야 한다.

라이선스: VLZ 는 각 로고의 상표권을 원권리자에게 두고 배포한다.
세모로고도 식별·참조 목적의 디렉터리이므로 동일한 전제로 다룬다.

  python3 scripts/collect-wordmarks-vlz.py --dry-run
  python3 scripts/collect-wordmarks-vlz.py --limit 20
  python3 scripts/collect-wordmarks-vlz.py
"""
import json, re, sys, time, collections, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
TREE = "https://api.github.com/repos/VectorLogoZone/vectorlogozone/git/trees/main?recursive=1"
RAW = "https://raw.githubusercontent.com/VectorLogoZone/vectorlogozone/main/{path}"
UA = "VibersLogoCollector/1.0 (https://semologo.com)"

def get(url, timeout=90):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout).read()

def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def main():
    dry = "--dry-run" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

    tree = json.loads(get(TREE))
    vlz = collections.defaultdict(dict)
    for x in tree.get("tree", []):
        m = re.match(r"src/content/logos/([^/]+)/\1-([a-z0-9]+)\.svg$", x["path"])
        if m:
            vlz[m.group(1)][m.group(2)] = x["path"]

    wn = {}
    for slug, forms in vlz.items():
        f = forms.get("ar21") or forms.get("wordmark") or forms.get("horizontal")
        if not f:
            continue
        n = norm(slug)
        if len(n) >= 3:
            wn.setdefault(n, (slug, f))

    idx = json.load(open(C / "variants-index.json"))["brands"]
    slim = json.load(open(C / "brands-slim.json"))
    slim = slim["brands"] if isinstance(slim, dict) else slim
    m = {x["id"]: x for x in slim}

    todo = []
    for bid, v in idx.items():
        if tuple(sorted(v.get("forms") or [])) != ("symbol",):
            continue
        x = m.get(bid)
        if not x:
            continue
        for cand in (bid, bid.replace("-icon", ""), x.get("name_en")):
            n = norm(cand)
            if len(n) < 3:
                continue
            t = wn.get(n)
            if t:
                out = C / bid / "sources" / "vlz" / "wide.svg"
                if not out.exists():
                    todo.append((bid, t[0], t[1], out))
                break

    print(f"VLZ 가로형 {len(wn):,}슬러그 / 심볼만 브랜드와 매칭 {len(todo):,}건")
    if limit:
        todo = todo[:limit]
    if dry or not todo:
        for bid, slug, _, _ in todo[:15]:
            print(f"  {bid:<26} ← vlz:{slug}")
        return 0

    ok = fail = 0
    for i, (bid, slug, path, out) in enumerate(todo, 1):
        try:
            data = get(RAW.format(path=path), timeout=30)
            if b"<svg" not in data[:400].lower():
                raise ValueError("SVG 아님")     # 404 HTML 을 파일로 저장하지 않는다
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ❌ {bid} ← {slug}: {type(e).__name__}")
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
        time.sleep(0.12)

    # ⚠️ sources 등록까지 해야 매니페스트가 본다
    bp = C / "brands.json"
    data = json.load(open(bp))
    bl = data["brands"] if isinstance(data, dict) else data
    bm = {b["id"]: b for b in bl}
    reg = 0
    for bid, _s, _p, out in todo:
        if not out.exists():
            continue
        b = bm.get(bid)
        if not b:
            continue
        rel = "sources/vlz/wide.svg"
        srcs = b.setdefault("sources", [])
        if any(s.get("file") == rel for s in srcs):
            continue
        srcs.append({"provider": "vectorlogozone", "file": rel, "label": "가로조합형"})
        reg += 1
    if reg:
        json.dump(data, open(bp, "w"), ensure_ascii=False, indent=2)
    print(f"✅ 수집 {ok}건 · sources 등록 {reg}건" + (f" | 실패 {fail}건" if fail else ""))
    print("   다음: build-logo-variants.py → build-slim.py → sync-all-bucket.py")
    return 1 if fail else 0

sys.exit(main())
