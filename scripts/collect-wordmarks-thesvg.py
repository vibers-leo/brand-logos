#!/usr/bin/env python3
"""
심볼만 있는 브랜드에 theSVG 의 워드마크(텍스트) 판을 채운다.

왜 —
브랜드 8,640개가 심볼 하나뿐이라 "글자 들어간 로고"를 받을 수 없었다
(인스타그램·애플·구글·틱톡 등). theSVG 레지스트리에는 wordmark variant 가
375 슬러그에 있고, 우리 심볼-only 브랜드와 181건이 겹친다.

⚠️ 매칭 시 3자 미만 키는 버린다. 한글 브랜드명을 정규화하면 빈 문자열이
   되는데, 그걸 키로 쓰면 서로 다른 브랜드가 한 슬러그로 뭉친다
   (실측: 녹색사민당·앱스플라이어·밴드·오늘의집이 전부 mixue 로 매칭됐다).

대표 logo.svg 는 건드리지 않는다 — sources/thesvg/ 에 추가만 하고
variants 매니페스트가 형태별 선택지를 만든다.

  python3 scripts/collect-wordmarks-thesvg.py --dry-run
  python3 scripts/collect-wordmarks-thesvg.py --limit 20
  python3 scripts/collect-wordmarks-thesvg.py
"""
import json, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
REG = "https://thesvg.org/api/registry.json"
SVG = "https://thesvg.org/icons/{slug}/{variant}.svg"
UA = "VibersLogoCollector/1.0 (https://semologo.com)"

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read()

def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def main():
    dry = "--dry-run" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    reg = json.loads(get(REG))
    items = reg if isinstance(reg, list) else (reg.get("icons") or list(reg.values())[0])
    wm = {}
    for x in items:
        if "wordmark" not in x.get("variants", []):
            continue
        for k in [x["slug"]] + (x.get("aliases") or []):
            n = norm(k)
            if len(n) >= 3:            # ⚠️ 짧은/빈 키는 오매칭의 원인
                wm.setdefault(n, x)

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
            t = wm.get(n)
            if t:
                out = C / bid / "sources" / "thesvg" / "wordmark.svg"
                if not out.exists():
                    todo.append((bid, t["slug"], out))
                break

    print(f"theSVG 워드마크 {len(wm):,}슬러그 / 심볼만 브랜드와 매칭 {len(todo):,}건")
    if limit:
        todo = todo[:limit]
    if dry or not todo:
        for bid, slug, _ in todo[:15]:
            print(f"  {bid:<26} ← thesvg:{slug}")
        return 0

    ok = fail = 0
    for i, (bid, slug, out) in enumerate(todo, 1):
        try:
            data = get(SVG.format(slug=slug, variant="wordmark"), timeout=30)
            if b"<svg" not in data[:400].lower():
                raise ValueError("SVG 아님")           # 404 HTML 을 파일로 저장하지 않는다
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ❌ {bid} ← {slug}: {type(e).__name__}")
        if i % 20 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
        time.sleep(0.15)
    # ⚠️ 파일만 놓으면 매니페스트가 못 본다.
    #    build-logo-variants.py 는 디스크를 스캔하지 않고 brands.json 의
    #    sources[] 배열을 읽는다. 등록을 빠뜨리면 수집해도 형태가 안 늘어난다
    #    (실측: 181건 받아놓고 '변경 없음 37,608' 이 나왔다).
    bp = C / "brands.json"
    data = json.load(open(bp))
    bl = data["brands"] if isinstance(data, dict) else data
    bm = {b["id"]: b for b in bl}
    reg = 0
    for bid, _slug, out in todo:
        if not out.exists():
            continue
        b = bm.get(bid)
        if not b:
            continue
        rel = "sources/thesvg/wordmark.svg"
        srcs = b.setdefault("sources", [])
        if any(s.get("file") == rel for s in srcs):
            continue
        srcs.append({"provider": "thesvg", "file": rel, "label": "워드마크형"})
        reg += 1
    if reg:
        json.dump(data, open(bp, "w"), ensure_ascii=False, indent=2)
    print(f"✅ 수집 {ok}건 · sources 등록 {reg}건" + (f" | 실패 {fail}건" if fail else ""))
    print("   다음: python3 scripts/build-logo-variants.py → build-slim.py")
    return 1 if fail else 0

sys.exit(main())
