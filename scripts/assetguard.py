#!/usr/bin/env python3
"""
에셋 저장 가드 — 확장자와 실제 내용이 다르면 저장하지 않는다.

왜 필요한가:
  수집 대상 사이트가 404 를 200 + HTML 로 돌려주는 일이 흔하다(특히 쇼핑몰·
  GitHub Pages). 그걸 그대로 `logo.svg` 로 저장하면 **열리지 않는 SVG** 가
  DB 에 등록되고, `logo_svg=true` 라 사이트가 깨진 이미지를 렌더한다.

  2026-08-11 에 9건이 이 상태로 발견됐다 — zigzag·cosrx·fila-co 등에
  쇼핑몰 HTML 이 최대 730KB 짜리 `logo.svg` 로 들어가 있었다.
  같은 사고가 반복돼서 저장 지점에 공통 가드를 둔다.

사용:
    from assetguard import safe_write
    if not safe_write(path, data):
        continue          # 저장 안 됨 — 실패로 처리한다
"""
from __future__ import annotations
import sys
from pathlib import Path

# 너무 작은 파일은 아이콘 조각이거나 빈 응답이다.
MIN_BYTES = {".svg": 200, ".png": 500, ".jpg": 500, ".jpeg": 500, ".webp": 300}


def sniff(data: bytes) -> str:
    """매직바이트로 실제 형식을 판별한다. 확장자를 믿지 않는다."""
    head = data[:512]
    low = head.lower().lstrip()
    if low.startswith(b"<!doctype html") or low.startswith(b"<html"):
        return "html"
    if b"<svg" in head[:400].lower():
        return "svg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"RIFF") and b"WEBP" in head[:20]:
        return "webp"
    if head.startswith(b"GIF8"):
        return "gif"
    if head.startswith(b"%PDF"):
        return "pdf"
    # XML 선언으로 시작하는 SVG (<?xml ... ?><svg>)
    if low.startswith(b"<?xml") and b"<svg" in data[:2000].lower():
        return "svg"
    return "unknown"


def check(path: str | Path, data: bytes) -> tuple[bool, str]:
    """(저장해도 되는가, 사유)"""
    p = Path(path)
    ext = p.suffix.lower()
    if not data:
        return False, "빈 응답"
    lo = MIN_BYTES.get(ext)
    if lo and len(data) < lo:
        return False, f"너무 작음 ({len(data)}B < {lo}B)"
    kind = sniff(data)
    if kind == "html":
        return False, "내용이 HTML (404 페이지를 받았을 가능성)"
    want = {".svg": "svg", ".png": "png", ".jpg": "jpg",
            ".jpeg": "jpg", ".webp": "webp"}.get(ext)
    if want and kind != want:
        return False, f"확장자 {ext} 인데 내용은 {kind}"
    return True, kind


def safe_write(path: str | Path, data: bytes, *, quiet: bool = False) -> bool:
    """검사를 통과할 때만 쓴다. 통과 못 하면 **쓰지 않고 False**."""
    ok, why = check(path, data)
    if not ok:
        if not quiet:
            print(f"   ⛔ 저장 거부 {path} — {why}", file=sys.stderr)
        return False
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return True


if __name__ == "__main__":
    # 자체 점검
    cases = [
        ("logo.svg", b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h10v10H0z"/></svg>' * 3, True),
        ("logo.svg", b"<!doctype html><html><head><title>404</title></head></html>" * 20, False),
        ("logo.svg", b"<svg>", False),                       # 너무 작음
        ("logo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 600, True),
        ("logo.png", b'<svg xmlns="http://www.w3.org/2000/svg"></svg>' * 30, False),  # 확장자 불일치
        ("logo.svg", b"", False),
    ]
    bad = 0
    for name, data, want in cases:
        ok, why = check(name, data)
        mark = "✅" if ok == want else "❌"
        if ok != want:
            bad += 1
        print(f"  {mark} {name:10} {len(data):>6}B → {'허용' if ok else '거부'} ({why})")
    print("자체 점검 실패 0건" if not bad else f"자체 점검 실패 {bad}건")
    sys.exit(1 if bad else 0)
