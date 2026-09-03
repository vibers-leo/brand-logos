#!/usr/bin/env python3
"""검토 큐(_clients/_svg-review/)에서 눈검사를 통과한 SVG 를 실제 logo.svg 로 올린다.

upgrade-to-svg.py 는 기존 PNG 와 모양이 다른 SVG 를 자동 승격하지 않고
여기(검토 큐)에 둔다. 모양 비교는 '다른 브랜드'와 '같은 브랜드 다른 형태'를
못 가르기 때문이다(정답셋에서 정상 20건 중 12건을 버렸다).

  python3 scripts/promote-reviewed.py --sheet            # 후보 시트 (위 PNG / 아래 SVG)
  python3 scripts/promote-reviewed.py pooq-co,airbnb-co  # 통과한 것만 승격
  python3 scripts/promote-reviewed.py --reject alias     # 틀린 것 — svg-wanted 에 사유 기록
승격·거부 모두 큐에서 지운다. 남은 파일은 아직 판정 전이다.
"""
import sys, json, time, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import atomic_json, safesvg

C = Path(__file__).resolve().parent.parent / "_clients"
Q = C / "_svg-review"


def sheet():
    import cairosvg
    from PIL import Image, ImageDraw
    ids = sorted(p.stem for p in Q.glob("*.svg"))
    if not ids:
        print("큐 비어 있음"); return
    CELL, COLS = 150, 7
    rows = (len(ids) + COLS - 1) // COLS
    out = Image.new("RGB", (CELL * COLS + 10, (CELL * 2 + 34) * rows + 26), "#f4f4f5")
    d = ImageDraw.Draw(out)
    d.text((6, 6), "위=기존 PNG  아래=후보 SVG  (왼 흰/오 검정)", fill="#111")
    def card(im):
        c = Image.new("RGB", (CELL - 10, CELL - 10), "#fff")
        ImageDraw.Draw(c).rectangle([(CELL - 10) // 2, 0, CELL - 10, CELL - 10], fill="#18181b")
        im = im.convert("RGBA"); im.thumbnail((CELL - 40, CELL - 40))
        c.paste(im, ((CELL - 10 - im.width) // 2, (CELL - 10 - im.height) // 2), im); return c
    for n, bid in enumerate(ids):
        r, cix = divmod(n, COLS); y = 26 + r * (CELL * 2 + 34); x = cix * CELL + 8
        try: out.paste(card(Image.open(C / bid / "logo.png")), (x, y))
        except Exception: pass
        try:
            png = cairosvg.svg2png(bytestring=safesvg.sanitize(safesvg.inline_internal_entities(
                (Q / f"{bid}.svg").read_bytes())), output_width=300)
            out.paste(card(Image.open(io.BytesIO(png))), (x, y + CELL + 4))
        except Exception:
            d.text((x, y + CELL + 40), "렌더실패", fill="#c00")
        d.text((x, y + CELL * 2 + 8), bid[:18], fill="#555")
    p = Path("/tmp/svg-review.png"); out.save(p)
    print(f"✅ {p}  ({len(ids)}건)")


def promote(ids):
    ok = []
    for i in ids:
        src = Q / f"{i}.svg"
        if not src.exists():
            print(f"   {i}: 큐에 없음"); continue
        (C / i / "logo.svg").write_bytes(src.read_bytes()); src.unlink(); ok.append(i)
    if not ok: return
    with atomic_json.locked(C / "brands.json"):
        raw = json.loads((C / "brands.json").read_text())
        br = raw["brands"] if isinstance(raw, dict) else raw
        s = set(ok)
        for b in br:
            if b["id"] in s:
                b["has_svg"] = True; b["logo_svg"] = "logo.svg"
        if isinstance(raw, dict): raw["brands"] = br
        atomic_json.write_json(C / "brands.json", raw if isinstance(raw, dict) else br)
    print(f"✅ {len(ok)}건 승격 → build-variants.py --force --brand 로 파생물 재생성")


def reject(ids, why="홈페이지 SVG 가 다른 로고였다"):
    w = json.loads((C / "svg-wanted.json").read_text()); byid = {x["id"]: x for x in w}
    for i in ids:
        (Q / f"{i}.svg").unlink(missing_ok=True)
        e = byid.get(i) or {"id": i}
        e["failed_source"] = "site-svg-wrong"; e["failed_at"] = time.strftime("%Y-%m-%d"); e["note"] = why
        if i not in byid: w.append(e)
    atomic_json.write_json(C / "svg-wanted.json", w, indent=1)
    print(f"✅ {len(ids)}건 거부 기록")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "--sheet": sheet()
    elif a[0] == "--reject": reject(a[1].split(","))
    else: promote(a[0].split(","))
