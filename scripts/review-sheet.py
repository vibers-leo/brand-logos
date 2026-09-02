#!/usr/bin/env python3
"""수집한 로고를 눈으로 검사할 시트를 만든다.

⚠️ **회색 배경으로 그린다.** 흰 배경에 그리면 순백 로고가 안 보여
   '수집 실패'로 오해하고, 검은 배경에 그리면 검은 로고가 안 보인다.
   2026-09-02 에 흰 배경 시트로 보다가 191건 중 상당수를 잘못 판단할 뻔했다.

   중간 회색(#555)에서는 둘 다 보인다.

  python3 scripts/review-sheet.py --source krx-rendered --limit 40
  python3 scripts/review-sheet.py --ids a,b,c
"""
import json, os, random, sys
from pathlib import Path
from PIL import Image, ImageDraw

C = Path(__file__).resolve().parent.parent / "_clients"

def arg(k, d=None):
    return sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d

def main():
    src = arg("--source")
    ids = (arg("--ids") or "").split(",") if arg("--ids") else None
    limit = int(arg("--limit", "40"))
    out = arg("--out", "/tmp/review.png")

    brands = json.loads((C / "brands.json").read_text())["brands"]
    if ids:
        rows = [b for b in brands if b["id"] in ids]
    else:
        rows = [b for b in brands
                if (not src or (b.get("svg_source") or "") == src) and not b.get("hidden")]
        if len(rows) > limit:
            random.seed(int(arg("--seed", "1")))
            rows = random.sample(rows, limit)
    if not rows:
        print("  대상 없음"); return

    CELL, COLS = 170, 7
    n = len(rows); r = (n + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * CELL, r * (CELL + 20)), "white")
    dr = ImageDraw.Draw(sheet)
    for i, b in enumerate(rows):
        rr, cc = divmod(i, COLS)
        x, y = cc * CELL, rr * (CELL + 20)
        box = Image.new("RGB", (CELL - 6, CELL - 6), "#555")   # ★ 중간 회색
        for f in ("logo-transparent.png", "logo.png", "logo-800.png"):
            p = C / b["id"] / f
            if not p.exists():
                continue
            try:
                im = Image.open(p).convert("RGBA")
                im.thumbnail((CELL - 22, CELL - 22))
                box.paste(im, ((CELL - 6 - im.width) // 2, (CELL - 6 - im.height) // 2), im)
                break
            except Exception:
                continue
        sheet.paste(box, (x + 3, y + 3))
        dr.text((x + 4, y + CELL - 12), (b.get("name_ko") or b["id"])[:14], fill="black")
    sheet.save(out)
    print(f"  {n}건 → {out}")

main()
