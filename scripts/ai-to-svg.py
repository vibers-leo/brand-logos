#!/usr/bin/env python3
"""
ai-to-svg.py — Illustrator(.ai)·PDF·EPS 를 로고용 SVG 로 변환한다.

왜 Inkscape 인가:
  `.ai` 는 사실 두 종류다.
    · CS 이후 기본값 = **PDF 호환** 파일 → PDF 리더로 열린다
    · 아주 옛날 파일 = **EPS(PostScript)** 기반 → PDF 리더로 못 연다
  Inkscape 는 둘 다 읽고 **벡터를 벡터로** 유지한다. cairosvg·Pillow 는
  .ai 를 아예 못 읽고, 래스터로 굽는 방식은 확대하면 깨져서 로고에 못 쓴다.

크롭:
  `--export-area-drawing` 이 여백을 잘라 내용에 딱 맞춘다. 좌표를 다시
  쓰는 게 아니라 **캔버스를 줄이는 것**이라 벡터가 손상되지 않는다.

인쇄용 색상 프로파일 제거 (기본값):
  인쇄용 CI 파일(.ai)에는 CMYK ICC 프로파일이 통째로 박혀 있는 경우가 많다.
  실측: 애터미 CI → 변환 결과 922KB 중 **915KB 가 ICC 프로파일**이었다
  (`Japan Color 2001 Coated`). 웹에서는 쓰이지 않고 `icc-color()` 참조도 0건이라
  순수한 죽은 무게다. 지우면 922KB → 7KB. 참조가 있으면 지우지 않는다.

텍스트 → 윤곽선 (기본값):
  변환하면 글자가 `<text font-family="Helvetica">` 로 남는다. 그 폰트가 없는
  기기에서는 **로고가 다른 글꼴로 렌더된다** — 로고 파일로는 치명적이다.
  `--export-text-to-path` 로 글자를 도형으로 굳혀 어디서든 같게 보이게 한다.
  편집 가능한 텍스트가 필요하면 `--keep-text`.

사용:
    python3 scripts/ai-to-svg.py 로고.ai
    python3 scripts/ai-to-svg.py 로고.ai -o _clients/brand/logo.svg
    python3 scripts/ai-to-svg.py *.ai --outdir out/      # 여러 개
    python3 scripts/ai-to-svg.py 로고.ai --no-crop       # 여백 유지
"""
from __future__ import annotations
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assetguard import sniff, safe_write   # 저장 전 매직바이트 검사를 재사용한다

INKSCAPE = shutil.which("inkscape")
PDFTOCAIRO = shutil.which("pdftocairo")


def detect(path: Path) -> str:
    """.ai 가 PDF 호환인지 EPS 기반인지 — 실패했을 때 원인을 말해주기 위해."""
    head = path.read_bytes()[:1024]
    if head.startswith(b"%PDF"):
        return "pdf호환"
    if head.startswith(b"%!PS"):
        return "eps기반"
    if b"<svg" in head[:400].lower():
        return "이미svg"
    return "알수없음"


def convert(src: Path, dst: Path, crop: bool = True, outline_text: bool = True) -> tuple[bool, str]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.svg")

    if INKSCAPE:
        cmd = [INKSCAPE, "--export-type=svg", "--export-plain-svg",
               f"--export-filename={tmp}"]
        if crop:
            cmd.append("--export-area-drawing")
        if outline_text:
            cmd.append("--export-text-to-path")
        cmd.append(str(src))
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        if tmp.exists() and tmp.stat().st_size > 0:
            data = tmp.read_bytes()
            tmp.unlink()
            if sniff(data) != "svg":
                return False, "Inkscape 출력이 SVG 가 아님"
            if not safe_write(dst, data):
                return False, "저장 가드가 거부"
            return True, "inkscape"
        err = (r.stderr or b"").decode("utf-8", "ignore").strip().split("\n")[-1][:120]
        # PDF 호환 파일이면 poppler 로 한 번 더 시도한다
        if PDFTOCAIRO and detect(src) == "pdf호환":
            r2 = subprocess.run([PDFTOCAIRO, "-svg", str(src), str(tmp)],
                                capture_output=True, timeout=180)
            if tmp.exists() and tmp.stat().st_size > 0:
                data = tmp.read_bytes(); tmp.unlink()
                if safe_write(dst, data):
                    return True, "pdftocairo"
        return False, f"Inkscape 실패: {err or '출력 없음'}"

    return False, "Inkscape 가 없다 (brew install --cask inkscape)"


def strip_icc(svg: Path) -> int:
    """참조되지 않는 ICC 색상 프로파일을 걷어낸다. 줄어든 바이트를 돌려준다.

    `icc-color(...)` 로 실제 참조하는 곳이 있으면 색이 달라질 수 있으므로
    건드리지 않는다."""
    t = svg.read_text(errors="ignore")
    if "icc-color(" in t:
        return 0                      # 실제로 쓰고 있다 — 손대지 않는다
    before = len(t)
    out = re.sub(r"<color-profile\b[^>]*/>", "", t)
    out = re.sub(r"<color-profile\b.*?</color-profile>", "", out, flags=re.S)
    if len(out) == before:
        return 0
    svg.write_text(out)
    return before - len(out)


def describe(svg: Path) -> str:
    """변환 결과가 쓸만한지 — 경로가 실제로 들어있는지 본다."""
    t = svg.read_text(errors="ignore")
    paths = t.count("<path") + t.count("<polygon") + t.count("<circle") + t.count("<rect")
    has_img = "<image" in t          # 벡터가 아니라 래스터가 박힌 경우
    vb = ""
    if 'viewBox="' in t:
        vb = t.split('viewBox="', 1)[1].split('"', 1)[0]
    note = f"도형 {paths}개"
    if has_img:
        note += " ⚠️ 래스터 이미지 포함(원본이 벡터가 아닐 수 있음)"
    if "<text" in t:
        note += " ⚠️ <text> 남음 — 폰트 없는 기기에서 다르게 보인다"
    if vb:
        note += f" · viewBox {vb}"
    return note


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help=".ai / .pdf / .eps")
    ap.add_argument("-o", "--out", help="출력 파일 (입력이 하나일 때)")
    ap.add_argument("--outdir", help="출력 폴더 (여러 개일 때)")
    ap.add_argument("--no-crop", action="store_true", help="여백을 자르지 않는다")
    ap.add_argument("--keep-icc", action="store_true",
                    help="인쇄용 ICC 색상 프로파일을 남긴다 (기본은 참조 없으면 제거)")
    ap.add_argument("--keep-text", action="store_true",
                    help="글자를 <text> 로 남긴다 (기본은 윤곽선 변환 — 폰트 없는 기기에서 깨지지 않게)")
    a = ap.parse_args()

    srcs = [Path(f) for f in a.files]
    if a.out and len(srcs) > 1:
        print("-o 는 입력이 하나일 때만 씁니다. 여러 개면 --outdir 을 쓰세요.")
        return 2

    ok = fail = 0
    for s in srcs:
        if not s.exists():
            print(f"  ❌ {s} — 파일 없음"); fail += 1; continue
        kind = detect(s)
        if a.out:
            dst = Path(a.out)
        elif a.outdir:
            dst = Path(a.outdir) / (s.stem + ".svg")
        else:
            dst = s.with_suffix(".svg")

        good, how = convert(s, dst, crop=not a.no_crop, outline_text=not a.keep_text)
        if good and not a.keep_icc:
            saved = strip_icc(dst)
            if saved:
                print(f"      🧹 참조 없는 색상 프로파일 제거 — {saved/1024:.0f}KB 절약")
        if good:
            print(f"  ✅ {s.name} [{kind}] → {dst}  ({how}, {dst.stat().st_size:,}B)")
            print(f"      {describe(dst)}")
            ok += 1
        else:
            hint = ""
            if kind == "eps기반":
                hint = "  (아주 오래된 EPS 기반 .ai 입니다. Illustrator 에서 다시 저장해 주세요)"
            print(f"  ❌ {s.name} [{kind}] — {how}{hint}")
            fail += 1

    print(f"\n성공 {ok} / 실패 {fail}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
