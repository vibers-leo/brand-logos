#!/usr/bin/env python3
"""검토 큐(_clients/_svg-review)의 '시트 SVG' 에서 로고 하나를 viewBox 크롭으로 떼어낸다.

CI 매뉴얼 PDF·색상 변형 그리드·A4 한 장짜리 심볼 안내는 진짜 벡터인데 로고가 아니라
**페이지**다. 경로를 수술하지 않고 viewBox 만 바꾸면 무손실로 로고만 남는다
(올루올루·부산 파트너 로고와 같은 방식). 렌더한 뒤 잉크 덩어리를 뭉쳐 후보를 번호로 보여준다.

  python3 scripts/crop-sheet.py                      # 큐 전체 → /tmp/crop-candidates.png (번호 대조표)
  python3 scripts/crop-sheet.py --ids koem,kinsre
  python3 scripts/crop-sheet.py --pick koem=3 --as logo          # 후보 3 → logo.svg 로 승격
  python3 scripts/crop-sheet.py --pick cbnuac=1 --as symbol      # → variants/symbol.svg (+override)
  python3 scripts/crop-sheet.py --pick jgego=2 --as vertical     # → variants/vertical.svg (+override)

⚠️ <svg> 의 width/height 는 반드시 둘 다 지운다. re.sub(count=2) 는 한 번의 스캔이라
   width 를 지우고 나면 height 를 못 잡는다 — 2026-09-06 에 그래서 크롭이 통째로 무시됐다.
"""
import argparse, io, json, re, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import safesvg, cairosvg, atomic_json
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

C = Path(__file__).resolve().parent.parent / "_clients"; Q = C / "_svg-review"
RW = 1400          # 분석 렌더 폭
JOIN = 22          # 이 픽셀 안의 덩어리는 한 로고(심볼+워드마크)로 뭉친다
PAD = 0.06         # 크롭 여백 (후보 상자 대비)

def render(svg_bytes, w):
    png = cairosvg.svg2png(bytestring=safesvg.sanitize(safesvg.inline_internal_entities(svg_bytes)), output_width=w)
    return Image.open(io.BytesIO(png)).convert("RGBA")

def candidates(svg_bytes):
    im = render(svg_bytes, RW); a = np.array(im)
    ink = (a[..., 3] > 30) & (a[..., :3].sum(-1) < 735)
    lab, n = ndimage.label(ndimage.binary_dilation(ink, iterations=JOIN))
    W, H = im.size; out = []
    for o in ndimage.find_objects(lab):
        x0, x1, y0, y1 = o[1].start, o[1].stop, o[0].start, o[0].stop
        if (x1 - x0) < W * 0.03 or (y1 - y0) < H * 0.015: continue    # 캡션 한 줄·점 같은 것
        sub = ink[y0:y1, x0:x1]; ys, xs = np.where(sub)
        # 팽창 여백을 걷어내고 실제 잉크 상자로
        bx0, bx1, by0, by1 = x0 + xs.min(), x0 + xs.max() + 1, y0 + ys.min(), y0 + ys.max() + 1
        out.append(dict(rel=((bx0) / W, by0 / H, bx1 / W, by1 / H), ink=float(sub.mean()), area=(bx1 - bx0) * (by1 - by0) / (W * H)))
    out.sort(key=lambda c: -c["area"])
    return im, out

def crop_svg(svg_text, rel):
    m = re.search(r"<svg[^>]*>", svg_text); root = m.group(0)
    vb = re.search(r'viewBox="([^"]+)"', root)
    if vb: vx, vy, vw, vh = map(float, vb.group(1).replace(",", " ").split())
    else:
        vw = float(re.search(r'width="([\d.]+)', root).group(1)); vh = float(re.search(r'height="([\d.]+)', root).group(1)); vx = vy = 0.0
    x0, y0, x1, y1 = rel; pw, ph = (x1 - x0) * PAD, (y1 - y0) * PAD
    x0, y0, x1, y1 = max(0, x0 - pw), max(0, y0 - ph), min(1, x1 + pw), min(1, y1 + ph)
    nb = f"{vx + vw * x0:.3f} {vy + vh * y0:.3f} {vw * (x1 - x0):.3f} {vh * (y1 - y0):.3f}"
    root2 = re.sub(r'\s(width|height)="[^"]*"', "", root)           # 둘 다 — 단일 스캔 함정 회피
    root2 = re.sub(r'viewBox="[^"]+"', f'viewBox="{nb}"', root2) if vb else root2.replace("<svg", f'<svg viewBox="{nb}"', 1)
    assert "width=" not in root2 and "height=" not in root2
    return svg_text[:m.start()] + root2 + svg_text[m.end():]

def sheet(ids, out):
    CELL = 300; rows = []
    for bid in ids:
        p = Q / f"{bid}.svg"
        if not p.exists(): print(f"  {bid}: 큐에 없음"); continue
        im, cands = candidates(p.read_bytes()); rows.append((bid, im, cands))
    if not rows: return
    img = Image.new("RGB", (CELL * 2 + 10 + 8 * (CELL // 2), max(1, len(rows)) * (CELL + 30)), "#f4f4f5"); d = ImageDraw.Draw(img)
    for r, (bid, im, cands) in enumerate(rows):
        y = r * (CELL + 30)
        page = im.copy(); page.thumbnail((CELL * 2, CELL)); pg = Image.new("RGB", page.size, "#fff"); pg.paste(page, (0, 0), page); pd = ImageDraw.Draw(pg)
        for i, c in enumerate(cands[:8]):
            x0, y0, x1, y1 = c["rel"]; W, H = pg.size
            pd.rectangle([x0 * W, y0 * H, x1 * W, y1 * H], outline="#e11d48", width=2); pd.text((x0 * W + 2, y0 * H + 1), str(i + 1), fill="#e11d48")
        img.paste(pg, (5, y + 5))
        for i, c in enumerate(cands[:8]):
            x0, y0, x1, y1 = c["rel"]; W, H = im.size
            cut = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))); cut.thumbnail((CELL // 2 - 12, CELL // 2 - 12))
            cell = Image.new("RGB", (CELL // 2 - 6, CELL // 2 - 6), "#fff"); cell.paste(cut, ((cell.width - cut.width) // 2, (cell.height - cut.height) // 2), cut)
            img.paste(cell, (CELL * 2 + 10 + i * (CELL // 2), y + 5)); d.text((CELL * 2 + 14 + i * (CELL // 2), y + CELL // 2 + 2), f"{i + 1}  {c['rel'][2]-c['rel'][0]:.2f}x{c['rel'][3]-c['rel'][1]:.2f}", fill="#333")
        d.text((8, y + CELL + 10), f"{bid}   후보 {len(cands)}개 (큰 순)", fill="#111")
    img.save(out); print(f"✅ {out}  ({len(rows)}건)")

def pick(spec, kind, label):
    bid, n = spec.split("="); n = int(n) - 1
    p = Q / f"{bid}.svg"
    if not p.exists():                                  # 앞선 픽이 시트를 sources/ci 로 옮긴 뒤 두 번째 변형을 뜰 때
        p = C / bid / "sources" / "ci" / f"ci-sheet-{bid}.svg"
    svg = p.read_text(errors="ignore")
    _, cands = candidates(p.read_bytes()); c = cands[n]
    out = crop_svg(svg, c["rel"]); d = C / bid
    im = render(out.encode(), 512); assert im.getbbox(), "크롭 결과가 비었다"
    (d / "sources" / "ci").mkdir(parents=True, exist_ok=True)
    src_keep = d / "sources" / "ci" / f"ci-sheet-{bid}.svg"
    today = time.strftime("%Y-%m-%d")
    if kind == "logo":
        (d / "logo.svg").write_text(out)
        with atomic_json.locked(C / "brands.json"):
            raw = json.loads((C / "brands.json").read_text()); br = raw["brands"] if isinstance(raw, dict) else raw
            for b in br:
                if b["id"] == bid: b["has_svg"] = True; b["logo_svg"] = "logo.svg"; b["svg_from"] = "ci-page-crop"
            (C / "brands.json").write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")))   # 저장소 관례: 한 줄 (indent 를 주면 diff 가 120만 줄이 된다)
        print(f"✅ {bid}: 후보 {n+1} → logo.svg  (이제 `python3 build-variants.py --force --brand {bid}`)")
    else:
        v = d / "variants"; v.mkdir(exist_ok=True)
        (v / f"{kind}.svg").write_text(out); im.save(v / f"{kind}-512.png", "PNG", optimize=True)
        ov_p = d / "variants.override.json"; ov = json.loads(ov_p.read_text()) if ov_p.exists() else {"variants": []}
        if not any(x.get("files", {}).get("svg") in ("logo.svg",) or x.get("files", {}).get("png") == "logo.png" for x in ov["variants"]):
            base = {"key": "primary", "form": "horizontal", "label": "기본형", "files": {"png": "logo.png"}}
            if (d / "logo.svg").exists(): base["files"]["svg"] = "logo.svg"; base["files"]["png"] = "logo-800.png"
            ov["variants"].insert(0, base)
        ov["variants"] = [x for x in ov["variants"] if x.get("key") != f"{kind}-crop"]
        ov["variants"].append({"key": f"{kind}-crop", "form": kind if kind in ("symbol", "vertical", "horizontal", "wordmark") else "unknown",
                               "lang": "none" if kind == "symbol" else "ko", "label": label or kind,
                               "files": {"svg": f"variants/{kind}.svg", "png": f"variants/{kind}-512.png"}})
        ov["note"] = f"CI 시트(sources/ci) viewBox 크롭 — {today}"
        ov_p.write_text(json.dumps(ov, ensure_ascii=False, indent=1))
        print(f"✅ {bid}: 후보 {n+1} → variants/{kind}.svg + override  (이제 `python3 scripts/build-logo-variants.py --brand {bid} --force`)")
    if p != src_keep: shutil.move(str(p), src_keep)   # 원본 시트는 sources/ci 로, 큐에서는 제거
    T = C.parent / "_targets" / ".ci-tried.json"; t = json.loads(T.read_text()) if T.exists() else {}
    t[bid] = {"at": today, "why": f"검토큐 → 크롭 승격({kind})"}; T.write_text(json.dumps(t, ensure_ascii=False, indent=0) + "\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ids"); ap.add_argument("--pick", action="append", default=[])
    ap.add_argument("--as", dest="kind", default="logo", help="logo | symbol | vertical | horizontal | wordmark"); ap.add_argument("--label", default="")
    ap.add_argument("--out", default="/tmp/crop-candidates.png"); a = ap.parse_args()
    if a.pick:
        for s in a.pick: pick(s, a.kind, a.label)
    else:
        ids = a.ids.split(",") if a.ids else sorted(p.stem for p in Q.glob("*.svg"))
        sheet(ids, a.out)
