#!/usr/bin/env python3
"""'거의 빈 이미지'로 판정된 로고를 눈으로 보게 시트로 만든다.

자동 판정만 믿으면 안 된다. 잉크가 0으로 나오는 이유가 두 가지다:
  ① 진짜 빈 파일 — 숨겨야 한다
  ② **흰색 로고** — 다크 배경용이라 정상이다. 흰 배경에 렌더하면 0 이 된다
둘은 흰 배경/검은 배경에 각각 그려 보면 바로 갈린다.

  python3 scripts/blank-logo-sheet.py            # /tmp/blank-sheet-N.png
"""
import json, os, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
import collect_krx_lib as L

CELL, COLS = 150, 10
d = json.load(open("_clients/_bad-logos.json"))["bad"]
items = [x for x in d if x[2] == "거의빈이미지"]
print(f"  대상 {len(items)}건")

def render(bid):
    base = f"_clients/{bid}"
    p = base + "/logo.svg" if os.path.exists(base + "/logo.svg") else base + "/logo.png"
    if not os.path.exists(p): return None
    try:
        if p.endswith(".svg"):
            import cairosvg, io
            png = cairosvg.svg2png(url=p, output_width=CELL - 20)
            return Image.open(io.BytesIO(png)).convert("RGBA")
        return Image.open(p).convert("RGBA")
    except Exception:
        return None

PER = 60
for page in range((len(items) + PER - 1) // PER):
    chunk = items[page*PER:(page+1)*PER]
    rows = (len(chunk) + COLS - 1) // COLS
    # 위 절반 흰 배경 / 아래 절반 검은 배경 — 흰 로고를 가려내려고
    sheet = Image.new("RGB", (COLS*CELL, rows*(CELL*2+18)), "white")
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sheet)
    for i, it in enumerate(chunk):
        r, c = divmod(i, COLS)
        x, y = c*CELL, r*(CELL*2+18)
        img = render(it[0])
        for j, bg in enumerate(["white", "black"]):
            box = Image.new("RGB", (CELL-4, CELL-4), bg)
            if img:
                t = img.copy(); t.thumbnail((CELL-24, CELL-24))
                box.paste(t, ((CELL-4-t.width)//2, (CELL-4-t.height)//2),
                          t if t.mode == "RGBA" else None)
            sheet.paste(box, (x+2, y+2+j*CELL))
        dr.text((x+4, y+CELL*2+2), str(it[0])[:22], fill="black")
    out = f"/tmp/blank-sheet-{page+1}.png"
    sheet.save(out); print(f"  ✅ {out} ({len(chunk)}건)")
