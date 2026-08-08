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

# 파비콘이 '뭉갠 스트립'인지 판정하는 기준.
# 가로로 긴 로고를 64x64에 통째로 넣으면 잉크가 가운데 얇은 띠로만 남는다.
# 캔버스의 이 비율보다 적게 차지하면 파비콘으로 못 쓴다고 본다.
ICON_INK_MIN = 0.20


def icon_ink_ratio(path: Path) -> float | None:
    """logo-icon.png 의 잉크 바운딩박스가 캔버스에서 차지하는 면적 비율."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    try:
        arr = np.asarray(Image.open(path).convert("RGBA"))
    except Exception:
        return None
    if arr.size == 0:
        return None
    a = arr.astype(np.int16)
    opaque = a[..., 3] > 25
    if opaque.size and float(opaque.mean()) <= 0.97:
        # 투명 배경이면 알파가 곧 잉크다 (흰색 로고를 놓치지 않기 위해)
        m = opaque
    else:
        rgb = a[..., :3]
        m = opaque & (((rgb.max(2) - rgb.min(2)) > 25) | (rgb.max(2) < 235))
    cols, rows = m.any(0), m.any(1)
    if not cols.any() or not rows.any():
        return 0.0
    import numpy as _np
    xs, ys = _np.where(cols)[0], _np.where(rows)[0]
    w = xs[-1] - xs[0] + 1
    h = ys[-1] - ys[0] + 1
    return float(w * h) / float(arr.shape[0] * arr.shape[1])


def main() -> int:
    brands = json.loads((BASE / "brands.json").read_text())["brands"]
    corrupt, mismatch, weak_icons = [], [], []

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

        # 파비콘이 판독 가능한가 — 가로형 로고를 통째로 욱여넣으면 얇은 띠가 된다
        icon = d / "logo-icon.png"
        if icon.exists():
            r = icon_ink_ratio(icon)
            if r is not None and r < ICON_INK_MIN:
                weak_icons.append((bid, r))

    # 대소문자만 다른 중복 id — GitHub Pages 는 대소문자를 구분하므로
    # 대문자 쪽은 항상 404 다. 맥에서는 파일시스템이 구분하지 않아 안 보인다.
    seen: dict[str, str] = {}
    case_dupes = []
    for b in brands:
        low = b["id"].lower()
        if low in seen and seen[low] != b["id"]:
            case_dupes.append(f'{b["id"]} ↔ {seen[low]}')
        seen.setdefault(low, b["id"])
    if case_dupes:
        print(f"⚠️  대소문자만 다른 중복 id {len(case_dupes)}건 (대문자 쪽은 CDN 404)")
        for c in case_dupes[:10]:
            print(f"   {c}")

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

    # 약한 파비콘은 '경고'다 — 실패로 다루지 않는다.
    # 심볼이 애초에 없는 워드마크 브랜드(coupang, Gmarket 등)는 고칠 방법이
    # 없으므로 exit 1 로 만들면 CI가 영구히 빨간 상태가 된다.
    # 대신 재수집 타겟 목록으로 떨궈서 다음 수집이 노릴 수 있게 한다.
    if weak_icons:
        weak_icons.sort(key=lambda x: x[1])
        print(f"⚠️  파비콘이 얇은 브랜드 {len(weak_icons)}개 (심볼 미수집 — 실패 아님)")
        for bid, r in weak_icons[:10]:
            print(f"   {bid} (잉크 {r*100:.0f}%)")
        if len(weak_icons) > 10:
            print(f"   ... 외 {len(weak_icons)-10}개")
        wanted = BASE / "variant-wanted.json"
        wanted.write_text(json.dumps({
            "note": "파비콘으로 쓸 심볼이 없는 브랜드. 심볼형 로고 재수집 타겟. "
                    "logo-icon.png 의 잉크가 캔버스의 20% 미만인 경우.",
            "threshold": ICON_INK_MIN,
            "count": len(weak_icons),
            "brands": [{"id": b, "icon_ink": round(r, 4)} for b, r in weak_icons],
        }, ensure_ascii=False, indent=2))
        print(f"   → {wanted.relative_to(BASE.parent)} 에 기록")

    if corrupt or mismatch:
        return 1
    print(f"✅ 에셋 검사 통과 — 브랜드 {len(brands):,}개")
    return 0

if __name__ == "__main__":
    sys.exit(main())
