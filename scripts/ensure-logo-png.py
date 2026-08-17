#!/usr/bin/env python3
"""SVG 는 있는데 logo.png 가 없는 브랜드를 채우고, 가짜 벡터를 PNG 로 내린다.

왜 필요한가 (2026-08-16 사고):
  `build-variants.py` 는 logo-800/icon/transparent/white 만 만들고
  **logo.png 는 이미 있다고 전제한다** (보통 수집기가 받아온 원본 래스터).
  위키데이터 수집기는 SVG 만 받으므로 그 전제가 깨졌고, 신규 231개 브랜드에서
  사이드바 PNG 다운로드가 전부 404 를 받고 있었다.

  또 하나: 껍데기만 SVG 이고 안에 비트맵이 박힌 파일이 18건 있었다
  (요플레 1.5MB, 국립민속박물관 634KB). "확대해도 깨짐 없음" 이라고 안내하는데
  실제로는 깨진다. SVG 로 치지 않는다.

수집기를 새로 만들 때마다 같은 함정을 밟지 않도록, 수집 뒤 이걸 한 번 돌린다.
멱등이라 여러 번 돌려도 안전하다.

사용:
  python3 scripts/ensure-logo-png.py               # logo.png 채우기
  python3 scripts/ensure-logo-png.py --demote-fake # 가짜 벡터도 함께 정리
  python3 scripts/ensure-logo-png.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"
BRANDS = BASE / "brands.json"
WANTED = BASE / "svg-wanted.json"

PNG_WIDTH = 400

# cairosvg 가 삼키지 못하는 것들
ENTITY = re.compile(r'<!ENTITY\s+(\S+)\s+"([^"]*)"\s*>')
DOCTYPE = re.compile(r"<!DOCTYPE[^\[>]*(\[.*?\])?\s*>", re.S)


def prepare(text: str) -> str:
    """렌더 전에 SVG 를 손봐 준다. 순서가 중요하다.

    · DTD 엔티티: **정의를 지우기 전에** 본문 참조를 실제 값으로 바꾼다.
      순서를 바꾸면 'undefined entity' 로 죽는다.
    · preserveAspectRatio 값이 하나뿐이면 cairosvg 가 unpack 에서 죽는다.
    · transform 안의 '0,5' 는 유럽 로케일이 만든 소수점 쉼표다.
      좌표 구분자와 헷갈리지 않게 앞뒤가 모두 숫자일 때만 바꾼다.
    """
    for name, val in ENTITY.findall(text):
        text = text.replace(f"&{name};", val)
    text = DOCTYPE.sub("", text)
    text = re.sub(r'preserveAspectRatio\s*=\s*"(x[A-Za-z]+)"',
                  r'preserveAspectRatio="\1 meet"', text)
    text = re.sub(r'((?:gradient|patternT|t)ransform="\s*)([^"]*)(")', _fix_decimal_comma,
                  text, flags=re.I)
    return text


def _fix_decimal_comma(m: re.Match) -> str:
    """유럽 로케일이 만든 소수점 쉼표만 되돌린다.

    ⚠️ 무조건 바꾸면 안 된다. `matrix(0.503,0,0,0.503,-11,-15)` 처럼 정상적인
    transform 의 **인자 구분 쉼표**까지 점이 되어 인자가 합쳐지고,
    cairosvg 가 'Matrix.__init__() takes from 1 to 7' 로 죽는다(실제로 겪었다).

    구분 기준: 이미 소수점(.)이 있으면 그 파일은 로케일 문제가 아니다.
    """
    body = m.group(2)
    if "." in body:
        return m.group(0)
    return m.group(1) + re.sub(r"(?<=\d),(?=\d)", ".", body) + m.group(3)


def is_raster_wrapped(svg: Path) -> bool:
    t = svg.read_text(errors="replace")
    return "data:image/" in t or "<image" in t


def render_png(svg: Path, out: Path) -> str | None:
    """성공하면 None, 실패하면 사유를 돌려준다."""
    import cairosvg
    from PIL import Image
    try:
        cairosvg.svg2png(bytestring=prepare(svg.read_text(errors="replace")).encode(),
                         write_to=str(out), output_width=PNG_WIDTH)
    except Exception as e:
        out.unlink(missing_ok=True)
        return f"{type(e).__name__}: {str(e)[:60]}"
    # cairosvg 는 렌더에 실패해도 조용히 빈 이미지를 뱉는다 — 잉크로 확인한다.
    # 상한은 두지 않는다: 블랙핑크·기아타이거즈처럼 배경이 꽉 찬 로고는
    # 잉크 100% 가 정상이다(예전에 상한 가드가 이런 걸 죽였다).
    im = Image.open(out).convert("RGBA")
    ink = sum(1 for p in im.split()[3].get_flattened_data() if p > 20) / (im.width * im.height)
    if ink <= 0.005:
        out.unlink(missing_ok=True)
        return f"빈 렌더 (잉크 {ink:.1%})"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demote-fake", action="store_true",
                    help="비트맵이 박힌 SVG 를 PNG 로 내리고 SVG 대기 목록에 올린다")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(BRANDS.read_text())
    brands = data["brands"] if isinstance(data, dict) else data

    demoted, made, failed = [], 0, []

    if args.demote_fake:
        for b in brands:
            svg = BASE / b["id"] / "logo.svg"
            if not svg.exists() or not is_raster_wrapped(svg):
                continue
            demoted.append(b)
            if args.dry_run:
                continue
            # ⚠️ 내리기 **전에** PNG 를 만든다. 안 그러면 SVG 를 옮긴 뒤
            #    "SVG 가 없어서" PNG 생성 루프가 건너뛰고, 브랜드에 자산이
            #    하나도 안 남는다 — 목록에서 사라지고 페이지가 죽는다
            #    (2026-08-17: 미라맥스·cnn-films 등 4건이 실제로 그렇게 됐다).
            png = BASE / b["id"] / "logo.png"
            if not png.exists():
                why = render_png(svg, png)
                if why:
                    print(f"   ⚠️ {b['id']}: 내리기 전 PNG 생성 실패 ({why}) — 건너뛴다")
                    demoted.pop()
                    continue
            keep = BASE / b["id"] / "sources" / "raster-wrapped" / "logo.svg"
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(svg), str(keep))      # 버리지 않는다 — 원본은 남긴다
            b.pop("logo_svg", None)
            b["has_svg"] = False
            b["svg_note"] = ("비트맵이 박힌 SVG 라 벡터로 쓸 수 없다. "
                             "sources/raster-wrapped/ 에 보관.")
            b["sources"] = [s for s in (b.get("sources") or []) if s.get("file") != "logo.svg"]

    for b in brands:
        d = BASE / b["id"]
        svg, png = d / "logo.svg", d / "logo.png"
        if png.exists() or not svg.exists():
            continue
        if args.dry_run:
            made += 1
            continue
        why = render_png(svg, png)
        if why:
            failed.append(f"{b['id']}: {why}")
        else:
            made += 1

    if not args.dry_run:
        for b in brands:
            if (BASE / b["id"] / "logo.png").exists():
                b["logo_png"] = True
                b["has_png"] = True
        BRANDS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")

        if demoted and WANTED.exists():
            w = json.loads(WANTED.read_text())
            have = {x["id"] for x in w["brands"]}
            new = [{"id": b["id"], "name_ko": b.get("name_ko"), "name_en": b.get("name_en"),
                    "category": b.get("category"), "domain": b.get("domain"),
                    "failed_source": "raster-wrapped-svg", "failed_at": time.strftime("%Y-%m-%d")}
                   for b in demoted if b["id"] not in have]
            if new:
                w["brands"] += new
                w["count"] = len(w["brands"])
                w["generated_at"] = time.strftime("%Y-%m-%d")
                WANTED.write_text(json.dumps(w, ensure_ascii=False, indent=1) + "\n")

    tag = "[dry-run] " if args.dry_run else ""
    print(f"{tag}logo.png 생성 {made}건 | 가짜 벡터 정리 {len(demoted)}건 | 실패 {len(failed)}건")
    for f in failed[:10]:
        print(f"   {f}")
    if demoted:
        print("   내림:", ", ".join((b.get("name_ko") or b["id"]) for b in demoted[:8]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
