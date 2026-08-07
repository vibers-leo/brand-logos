#!/usr/bin/env python3
"""
에셋 무결성 검사 — 커밋/배포 전에 돌린다.

잡아내는 것:
  1. 확장자와 내용이 다른 파일 (404 HTML이 logo.svg로 저장된 사고 방지)
  2. 빈 파일
  3. brands.json 표기와 실제 파일 불일치

실패 시 exit 1. CI에서 이 스크립트가 통과해야 커밋한다.
"""
import json, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"

def sniff(p: Path) -> str:
    if not p.exists() or p.stat().st_size == 0:
        return "MISSING"
    h = p.open("rb").read(512)
    hl = h.lower()
    # 대소문자 무시 — <!doctype html> 소문자로 오는 사이트가 있다
    if b"<!doctype html" in hl or hl.lstrip()[:5].startswith(b"<html"):
        return "HTML"
    if hl.lstrip().startswith(b"file not found") or hl.lstrip().startswith(b"not found"):
        return "ERRORTEXT"
    if b"<svg" in h.lower() or h.lstrip().startswith(b"<?xml"):
        return "SVG"
    if h[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if h[:3] == b"\xff\xd8\xff":
        return "JPEG"
    return "UNKNOWN"

def main() -> int:
    brands = json.loads((BASE / "brands.json").read_text())["brands"]
    corrupt, mismatch = [], []

    for b in brands:
        bid = b["id"]
        d = BASE / bid

        for svg in d.glob("*.svg"):
            k = sniff(svg)
            if k not in ("SVG", "MISSING"):
                corrupt.append(f"{svg.relative_to(BASE)} → 내용이 {k}")

        for png in d.glob("*.png"):
            k = sniff(png)
            if k not in ("PNG", "JPEG", "MISSING"):
                corrupt.append(f"{png.relative_to(BASE)} → 내용이 {k}")

        # brands.json 이 SVG 있다고 하는데 실제로 없거나 깨진 경우
        if (b.get("logo_svg") or b.get("has_svg")) and sniff(d / "logo.svg") != "SVG":
            mismatch.append(f"{bid}: logo_svg=true 인데 실제 SVG 없음")

    if corrupt:
        print(f"❌ 내용이 확장자와 다른 파일 {len(corrupt)}개")
        for c in corrupt[:40]:
            print(f"   {c}")
        if len(corrupt) > 40:
            print(f"   ... 외 {len(corrupt)-40}개")
    if mismatch:
        print(f"❌ brands.json 불일치 {len(mismatch)}개")
        for m in mismatch[:40]:
            print(f"   {m}")
        if len(mismatch) > 40:
            print(f"   ... 외 {len(mismatch)-40}개")

    if corrupt or mismatch:
        return 1
    print(f"✅ 에셋 검사 통과 — 브랜드 {len(brands):,}개")
    return 0

if __name__ == "__main__":
    sys.exit(main())
