#!/usr/bin/env python3
"""지자체 상징물 페이지의 **PDF·ZIP 배포파일**에서 로고를 꺼낸다.

미수집 66곳을 추적해 보니 8곳은 자산까지 찾아 놓고 등록을 못 했다.
자산이 이미지가 아니라 **CI 매뉴얼 PDF** 나 **ZIP 배포파일**이었기 때문이다.
수집기가 PNG·SVG 만 다뤄서 그대로 버려졌다.

PDF 는 두 방법으로 본다:
  ① `pdfimages` 로 내장 비트맵을 그대로 꺼낸다 — 원본 화질 그대로다
  ② 못 꺼내면 페이지를 렌더한 뒤 CI 시트 분리기로 로고 영역만 자른다
ZIP 은 풀어서 안의 이미지를 쓴다(AI·EPS 는 건드리지 않는다).

⛔ 2026-09-01 실측 — **이 방법은 실패했다. 그대로 쓰지 마라.**
   8곳 중 5곳에서 이미지를 뽑았지만 눈으로 보니 전부 로고가 아니었다:
     광주시  한국정보접근성인증 WA 마크
     보성군  재난 안내문 페이지
     여수시  검은 배경의 그래픽 조각
     순창군  사과밭 사진
     전주시  텍스트만 있는 신청서 페이지
   원인은 자산 수집 단계에 있다. `muni-symbols.json` 의 assets 는
   **상징물 페이지에 있는 모든 PDF 링크**를 긁은 것이라, CI 매뉴얼이 아니라
   접근성 인증마크·안내문·신청서가 대부분이다.

   고치려면 파일명이나 링크 텍스트로 CI 매뉴얼을 가려내야 하는데
   `20210223down_02.pdf` 같은 이름이 많아 그것만으론 안 된다.
   이 8곳은 브라우저로 직접 보는 편이 빠르다.

  python3 scripts/extract-muni-pdf.py --dry-run
  python3 scripts/extract-muni-pdf.py --apply
"""
import io, json, os, re, subprocess, sys, tempfile, zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import collect_krx_lib as L

C = Path("_clients")
MIN_PX = 120          # 이보다 작으면 아이콘 부스러기다
MAX_MB = 40

def fetch(url):
    try:
        data, ctype = L.get(url, timeout=40, limit=MAX_MB * 1024 * 1024)
        return data, (ctype or "").lower()
    except Exception as e:
        return None, f"err:{type(e).__name__}"

def images_from_pdf(data):
    """내장 비트맵 → 없으면 페이지 렌더. (PIL.Image, 출처) 목록."""
    from PIL import Image
    out = []
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.pdf"; p.write_bytes(data)
        # ① 내장 이미지
        try:
            subprocess.run(["pdfimages", "-png", "-f", "1", "-l", "3", str(p),
                            str(Path(td) / "im")], capture_output=True, timeout=90)
            for f in sorted(Path(td).glob("im-*.png")):
                try:
                    im = Image.open(f).convert("RGBA")
                    if min(im.size) >= MIN_PX: out.append((im, "내장"))
                except Exception:
                    pass
        except Exception:
            pass
        if out: return out[:8]
        # ② 페이지 렌더
        try:
            import fitz
            doc = fitz.open(str(p))
            for i in range(min(2, doc.page_count)):
                pix = doc[i].get_pixmap(dpi=200)
                out.append((Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA"),
                            f"p{i+1}렌더"))
            doc.close()
        except Exception:
            pass
    return out[:4]

def images_from_zip(data):
    from PIL import Image
    out = []
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return out
    for n in z.namelist():
        if not re.search(r"\.(png|jpg|jpeg|gif)$", n, re.I): continue
        if "__MACOSX" in n: continue
        try:
            im = Image.open(io.BytesIO(z.read(n))).convert("RGBA")
            if min(im.size) >= MIN_PX: out.append((im, f"zip:{Path(n).name[:24]}"))
        except Exception:
            pass
    return out[:8]

def main():
    apply_ = "--apply" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    targets = json.load(open("_targets/muni-symbols.json"))
    have = {b.get("name_ko") for b in
            json.load(open(str(C / "brands.json")))["brands"] if b.get("kr_kind") == "지자체"}
    todo = [t for t in targets
            if t["name"] not in have and t.get("assets")
            and any(re.search(r"\.(pdf|zip)(\?|$)", a, re.I) for a in t["assets"])]
    if only: todo = [t for t in todo if t["name"] == only]
    print(f"  대상 {len(todo)}곳")
    outdir = Path("/tmp/muni-pdf"); outdir.mkdir(exist_ok=True)
    for t in todo:
        got = []
        for url in t["assets"]:
            if not re.search(r"\.(pdf|zip)(\?|$)", url, re.I): continue
            data, ctype = fetch(url)
            if not data:
                print(f"   {t['name'][:14]:<16} ⚠️ 받기 실패 {ctype}"); continue
            if data[:4] == b"%PDF":  imgs = images_from_pdf(data)
            elif data[:2] == b"PK":  imgs = images_from_zip(data)
            else:
                print(f"   {t['name'][:14]:<16} ⚠️ PDF·ZIP 아님 ({data[:4]!r})"); continue
            got += imgs
            if got: break
        if not got:
            print(f"   {t['name'][:14]:<16} ❌ 이미지 없음"); continue
        # 잉크가 가장 많은 것을 대표로 (빈 여백 페이지 제외)
        import numpy as np
        best = None
        for im, src in got:
            a = np.array(im); rgb = a[..., :3].astype(int)
            ink = (a[..., 3] > 40) & (rgb.max(2) < 235)
            r = float(ink.mean())
            if 0.005 < r < 0.85 and (best is None or r > best[0]):
                best = (r, im, src)
        if not best:
            print(f"   {t['name'][:14]:<16} ❌ 쓸만한 이미지 없음 ({len(got)}장)"); continue
        r, im, src = best
        f = outdir / f"{t['name']}.png"
        im.save(f)
        print(f"   {t['name'][:14]:<16} ✅ {im.width}x{im.height} 잉크{r:.3f} [{src}] → {f}")

main()
