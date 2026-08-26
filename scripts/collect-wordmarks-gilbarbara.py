#!/usr/bin/env python3
"""
심볼만 있는 브랜드에 gilbarbara/logos 의 풀버전(심볼+글자)을 채운다.

왜 이 소스인가 —
logos.json 카탈로그가 파일 규칙을 명시한다: `{name}-icon.svg` = 심볼,
`{name}.svg` = 풀버전. 440개가 쌍을 갖고 있어 형태 매칭이 확실하다.
VLZ·theSVG 로 이미 채운 브랜드를 빼고도 693건이 남는다.

⚠️ 3자 미만 키는 버린다 — 한글명을 정규화하면 빈 문자열이 되어
   서로 다른 브랜드가 한 슬러그로 뭉친다.
⚠️ 파일만 받으면 반영되지 않는다. build-logo-variants.py 는 디스크가 아니라
   brands.json 의 sources[] 를 읽는다.

  python3 scripts/collect-wordmarks-gilbarbara.py --dry-run
  python3 scripts/collect-wordmarks-gilbarbara.py --limit 20
  python3 scripts/collect-wordmarks-gilbarbara.py
"""
import json, os, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
CATALOG = "https://raw.githubusercontent.com/gilbarbara/logos/main/logos.json"
RAW = "https://raw.githubusercontent.com/gilbarbara/logos/main/logos/{file}"
UA = "VibersLogoCollector/1.0 (https://semologo.com)"

def get(url, timeout=90):
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
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def main():
    dry = "--dry-run" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

    items = json.loads(get(CATALOG))
    items = items if isinstance(items, list) else (items.get("logos") or list(items.values())[0])
    gb = {}
    for x in items:
        full = [f for f in (x.get("files") or []) if not f.endswith("-icon.svg")]
        if not full:
            continue
        for k in (x.get("shortname"), x.get("name")):
            n = norm(k)
            if len(n) >= 3:
                gb.setdefault(n, (x["shortname"], full[0]))

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
        if (C / bid / "sources" / "vlz" / "wide.svg").exists() or \
           (C / bid / "sources" / "thesvg" / "wordmark.svg").exists():
            continue
        for cand in (bid, bid.replace("-icon", ""), x.get("name_en")):
            n = norm(cand)
            if len(n) < 3:
                continue
            t = gb.get(n)
            if t:
                out = C / bid / "sources" / "gilbarbara" / "full.svg"
                if not out.exists():
                    todo.append((bid, t[0], t[1], out))
                break

    print(f"gilbarbara 풀버전 {len(gb):,}키 / 신규 매칭 {len(todo):,}건")
    if limit:
        todo = todo[:limit]
    if dry or not todo:
        for bid, slug, _, _ in todo[:15]:
            print(f"  {bid:<26} ← gb:{slug}")
        return 0

    ok = fail = skip = 0
    for i, (bid, slug, f, out) in enumerate(todo, 1):
        try:
            data = get(RAW.format(file=f), timeout=30)
            if b"<svg" not in data[:400].lower():
                raise ValueError("SVG 아님")
            # ⚠️ '풀버전'이라고 다 글자가 있는 건 아니다. 원래 워드마크가 없는
            #    브랜드(Amazon Chime·아멕스 등)는 풀버전도 심볼과 같은 그림이다.
            #    같은 걸 한 번 더 실으면 다운로드 목록만 지저분해진다.
            #    글자가 붙으면 가로로 길어지므로 종횡비로 가른다(실측: 심볼 1.0 → 풀 2.6~3.1).
            cur = aspect(C / bid / "logo.svg")
            new_ar = aspect(data)
            if cur and new_ar and abs(new_ar - cur) < 0.4:
                skip += 1
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ❌ {bid} ← {slug}: {type(e).__name__}")
        if i % 50 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
        time.sleep(0.1)

    bp = C / "brands.json"
    data = json.load(open(bp))
    bl = data["brands"] if isinstance(data, dict) else data
    bm = {b["id"]: b for b in bl}
    reg = 0
    for bid, _s, _f, out in todo:
        if not out.exists():
            continue
        b = bm.get(bid)
        if not b:
            continue
        rel = "sources/gilbarbara/full.svg"
        srcs = b.setdefault("sources", [])
        if any(s.get("file") == rel for s in srcs):
            continue
        srcs.append({"provider": "gilbarbara", "file": rel, "label": "가로조합형"})
        reg += 1
    if reg:
        json.dump(data, open(bp, "w"), ensure_ascii=False, indent=2)
    print(f"✅ 수집 {ok}건 · 등록 {reg}건 · 중복 건너뜀 {skip}건" + (f" | 실패 {fail}건" if fail else ""))
    return 1 if fail else 0

sys.exit(main())
