#!/usr/bin/env python3
"""
에셋 무결성 검사 — 커밋/배포 전에 돌린다.

잡아내는 것:
  1. 확장자와 내용이 다른 파일 (404 HTML이 logo.svg로 저장된 사고 방지)
  2. 빈 파일
  3. brands.json 표기와 실제 파일 불일치

실패 시 exit 1. CI에서 이 스크립트가 통과해야 커밋한다.
"""
import json, re, sys
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
    missing_png, fake_vector, dead_variants = [], [], []

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

        # 표시 이름이 비면 화면이 죽는다. 2026-08-17 에 해외 영화사·투자사
        # 프리셋이 name_ko 에 null 을 그대로 써서, 초성을 한 글자만 쳐도
        # "Cannot read properties of null" 로 사이트 전체가 멈췄다.
        for k in ("name_ko", "name_en"):
            if not (b.get(k) or "").strip():
                mismatch.append(f"{bid}: {k} 가 비어 있다 (검색·표시가 깨진다)")
        if any(not isinstance(a, str) or not a.strip() for a in (b.get("aliases") or [])):
            mismatch.append(f"{bid}: aliases 에 빈 값이 있다")

        # ── 2026-08-16 에 실제로 터진 세 가지. 다시 나면 여기서 잡는다 ──

        # ① logo.png 가 없으면 PNG 다운로드 버튼이 404 를 받는다.
        #    build-variants 는 logo-800/icon/transparent 만 만들고 logo.png 는
        #    이미 있다고 전제한다. SVG 만 받아오는 수집기가 이걸 깨뜨렸고
        #    신규 231개 전부 다운로드가 실패했다.
        if (d / "logo.svg").exists() and not (d / "logo.png").exists():
            missing_png.append(bid)

        # ② 비트맵이 박힌 SVG 를 '벡터'라고 표시하면 거짓말이다.
        #    "확대해도 깨짐 없음" 이라고 안내하는데 실제로는 깨진다.
        if (b.get("logo_svg") or b.get("has_svg")) and (d / "logo.svg").exists():
            head = (d / "logo.svg").read_text(errors="replace")
            if "data:image/" in head or "<image" in head:
                fake_vector.append(bid)

        # ③ 변형 매니페스트가 없는 파일을 가리키면 눌러도 안 받아지는 버튼이 뜬다.
        vf = d / "variants.json"
        if vf.exists():
            try:
                for v in json.loads(vf.read_text()).get("variants", []):
                    for rel in (v.get("files") or {}).values():
                        if not (d / rel).exists():
                            dead_variants.append(f"{bid}: {rel}")
            except json.JSONDecodeError:
                corrupt.append(f"{bid}/variants.json → JSON 파싱 실패")

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
    # 경고가 아니라 실패로 다룬다. 맥은 대소문자를 구분하지 않아 로컬에서는
    # 두 폴더가 하나로 보이고, 리눅스·CDN 에서만 갈라진다. 실제로 daisyUI 는
    # 파일이 하나도 없는 채로 브랜드만 등록돼 CDN 404 였고 아무도 몰랐다
    # (2026-08-06 생성 → 2026-08-16 발견).
    #
    # ⚠️ 지울 때 `git rm -r _clients/{대문자}` 를 쓰면 안 된다. 맥에서는 같은
    #    파일이라 **소문자 원본까지 디스크에서 지워진다**(실제로 겪었다).
    #    `git rm --cached --sparse` 로 인덱스에서만 뺀다.
    if case_dupes:
        print(f"❌ 대소문자만 다른 중복 id {len(case_dupes)}건 (대문자 쪽은 CDN 404)")
        for c in case_dupes[:10]:
            print(f"   {c}")
        print("   → git rm --cached --sparse 로 인덱스에서만 뺀다 (git rm -r 은 원본까지 지운다)")

    # slug 에 QID 가 붙어 있으면 대개 중복이다. 예전 수집기가 slug 충돌을
    # QID 를 붙여 회피하는 바람에 daum ↔ daum-q493104 같은 중복이 41개 생겼다
    # (기존 항목 이름이 영문이라 이름 대조에도 안 걸렸다).
    ids = {b["id"] for b in brands}
    qid_dupes = [b["id"] for b in brands
                 if re.search(r"-q\d{4,}$", b["id"]) and re.sub(r"-q\d{4,}$", "", b["id"]) in ids]
    if qid_dupes:
        print(f"❌ QID 접미사 중복 {len(qid_dupes)}개 (같은 브랜드가 둘로 갈라져 있다)")
        for x in qid_dupes[:10]:
            # 정규식을 f-string 안에 두면 안 된다 — 파이썬 3.11 은 f-string
            # 표현식에 백슬래시를 허용하지 않는다 (CI 는 3.11, 로컬은 3.14였다)
            base = re.sub(r"-q\d{4,}$", "", x)
            print(f"   {x}  ↔  {base}")
        print("   → 기존 id 를 대표로 두고 신규 로고는 sources/ 변형으로 흡수한다")

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

    def report(items, title, hint):
        if not items:
            return
        print(f"❌ {title} {len(items)}개")
        for x in items[:20]:
            print(f"   {x}")
        if len(items) > 20:
            print(f"   ... 외 {len(items)-20}개")
        print(f"   → {hint}")

    report(missing_png, "logo.png 없음 (PNG 다운로드가 404 난다)",
           "python3 scripts/ensure-logo-png.py 로 SVG 에서 생성한다")
    report(fake_vector, "비트맵이 박힌 SVG 를 벡터라고 표시",
           "python3 scripts/ensure-logo-png.py --demote-fake 로 PNG 로 내린다")
    report(dead_variants, "변형 매니페스트가 없는 파일을 가리킴",
           "python3 scripts/build-logo-variants.py --force 로 재생성한다")

    if corrupt or mismatch or missing_png or fake_vector or dead_variants or case_dupes or qid_dupes:
        return 1
    print(f"✅ 에셋 검사 통과 — 브랜드 {len(brands):,}개")
    return 0

if __name__ == "__main__":
    sys.exit(main())
