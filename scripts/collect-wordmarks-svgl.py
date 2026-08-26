#!/usr/bin/env python3
"""
심볼만 있는 브랜드에 svgl.app 의 wordmark 판을 채운다.

왜 이 소스인가 —
지금까지 쓴 소스(VLZ·theSVG·gilbarbara)는 파일명 규칙이나 종횡비로
'글자가 있는 판'을 **추측**해야 했다. svgl 은 카탈로그에 `wordmark`
필드를 따로 두어 제공자가 직접 구분해 준다. 추측이 없으니 오답도 없다.
규모는 작다(666개 중 147개가 wordmark 보유) — 정확도로 얻는 소스다.

⚠️ wordmark 값이 문자열일 때도 dict{light,dark} 일 때도 있다.
   dict 면 light(밝은 배경용 = 진한 잉크)를 쓴다. 세모로고 카드가 흰 배경이다.
⚠️ 3자 미만 키는 버린다 — 한글명을 정규화하면 빈 문자열이 되어
   서로 다른 브랜드가 한 슬러그로 뭉친다.
⚠️ 파일만 받으면 반영되지 않는다. build-logo-variants.py 는 디스크가 아니라
   brands.json 의 sources[] 를 읽는다.

  python3 scripts/collect-wordmarks-svgl.py --dry-run
  python3 scripts/collect-wordmarks-svgl.py --limit 20
  python3 scripts/collect-wordmarks-svgl.py
"""
import json, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
API = "https://api.svgl.app"
UA = "VibersLogoCollector/1.0 (https://semologo.com)"

def get(url, timeout=60):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout).read()

def aspect(path_or_bytes):
    """SVG viewBox 의 가로/세로 비. 못 읽으면 None."""
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
    # svgl 의 id 는 정수다 — str() 없이 .lower() 하면 터진다
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())

def wordmark_url(x):
    w = x.get("wordmark")
    if not w:
        return None
    return w if isinstance(w, str) else (w.get("light") or w.get("dark"))

def main():
    dry = "--dry-run" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

    items = json.loads(get(API))
    cat = {}
    for x in items:
        u = wordmark_url(x)
        if not u:
            continue
        for k in (x.get("title"), x.get("id")):
            n = norm(k)
            if len(n) >= 3:
                cat.setdefault(n, (x.get("title"), u))

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
        # 다른 소스로 이미 채운 브랜드는 건너뛴다 (형태가 중복되면 목록만 지저분해진다)
        d = C / bid / "sources"
        if (d / "vlz" / "wide.svg").exists() or (d / "thesvg" / "wordmark.svg").exists() \
           or (d / "gilbarbara" / "full.svg").exists():
            continue
        for cand in (bid, bid.replace("-icon", ""), x.get("name_en")):
            n = norm(cand)
            if len(n) < 3:
                continue
            t = cat.get(n)
            if t:
                out = d / "svgl" / "wordmark.svg"
                if not out.exists():
                    todo.append((bid, t[0], t[1], out))
                break

    print(f"svgl wordmark {len(cat):,}키 / 신규 매칭 {len(todo):,}건")
    if limit:
        todo = todo[:limit]
    if dry or not todo:
        for bid, title, u, _ in todo[:15]:
            print(f"  {bid:<26} ← svgl:{title}")
        return 0

    ok = fail = skip = 0
    for i, (bid, title, u, out) in enumerate(todo, 1):
        try:
            data = get(u, timeout=30)
            if b"<svg" not in data[:400].lower():
                raise ValueError("SVG 아님")
            # 제공자가 wordmark 라고 표시했어도 심볼과 같은 그림인 경우가 있다.
            # 글자가 붙으면 가로로 길어지므로 종횡비로 한 번 더 거른다.
            cur, new_ar = aspect(C / bid / "logo.svg"), aspect(data)
            if cur and new_ar and abs(new_ar - cur) < 0.4:
                skip += 1
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ❌ {bid} ← {title}: {type(e).__name__}")
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
        time.sleep(0.1)

    # sources[] 등록 — 이걸 빠뜨리면 파일만 쌓이고 사이트에 안 나온다
    bp = C / "brands.json"
    data = json.load(open(bp))
    bl = data["brands"] if isinstance(data, dict) else data
    bm = {b["id"]: b for b in bl}
    reg = 0
    for bid, title, _u, out in todo:
        if not out.exists():
            continue
        b = bm.get(bid)
        if not b:
            continue
        rel = "sources/svgl/wordmark.svg"
        srcs = b.setdefault("sources", [])
        if any(s.get("file") == rel for s in srcs):
            continue
        srcs.append({"provider": "svgl", "file": rel, "label": "워드마크"})
        reg += 1
    bp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))

    print(f"\n✅ 수집 {ok}건 · 등록 {reg}건 · 중복 건너뜀 {skip}건 · 실패 {fail}건")
    print("   다음: build-logo-variants.py → build-slim.py → sync-all-bucket.py")
    return 0

if __name__ == "__main__":
    sys.exit(main())
