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
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"
BRANDS = BASE / "brands.json"
WANTED = BASE / "svg-wanted.json"
FAILURES = BASE / "png-render-failures.json"

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


ARGC = {"matrix": (6,), "translate": (1, 2), "scale": (1, 2),
        "rotate": (1, 3), "skewx": (1,), "skewy": (1,)}


def _args_valid(body: str) -> bool:
    """transform 값의 각 함수가 올바른 인자 개수와 형식을 갖췄는지 본다."""
    fns = re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", body)
    if not fns:
        return False
    for name, args in fns:
        want = ARGC.get(name.lower())
        if want is None:
            return False
        toks = [t for t in re.split(r"[\s,]+", args.strip()) if t]
        if len(toks) not in want:
            return False
        for t in toks:
            try:
                float(t)
            except ValueError:
                return False
    return True


def _fix_decimal_comma(m: re.Match) -> str:
    """유럽 로케일이 만든 소수점 쉼표만 되돌린다.

    ⚠️ 무조건 바꾸면 안 된다. `matrix(0.503,0,0,0.503,-11,-15)` 처럼 정상적인
    transform 의 **인자 구분 쉼표**까지 점이 되어 인자가 합쳐지고,
    cairosvg 가 'Matrix.__init__() takes from 1 to 7' 로 죽는다(실제로 겪었다).

    ⚠️ 예전 기준('점이 하나라도 있으면 건드리지 않는다')은 부족했다.
    `matrix(1,0,0,1,-70,-243)` 은 점이 없어서 통과했고 `matrix(1.0.0.1,...)` 로
    망가졌다 — 일러스트레이터가 늘 뱉는 형태라 165개 브랜드의 logo.png 가
    통째로 생성되지 않았고, 그 여파로 자동수집 워크플로까지 실패했다
    (2026-08-26).

    이제 **인자 개수로 판정한다.** 이미 유효하면 손대지 않고, 유효하지 않을
    때만 변환해 보고, 변환 결과가 유효해질 때만 채택한다. 개수는 모호하지 않다.
    """
    body = m.group(2)
    if _args_valid(body):
        return m.group(0)
    fixed = re.sub(r"(?<=\d),(?=\d)", ".", body)
    if _args_valid(fixed):
        return m.group(1) + fixed + m.group(3)
    return m.group(0)


def is_raster_wrapped(svg: Path) -> bool:
    t = svg.read_text(errors="replace")
    return "data:image/" in t or "<image" in t


# 한 파일이 배치 전체를 멈추는 걸 막는다.
# 2026-08-18: 4만 개 일괄 생성 중 cairosvg 가 거대 SVG 를 파싱하다 이차
# 시간 복잡도에 빠져 **6시간 40분을 한 파일에** 썼다(CPU 97%, 산출물 0).
# 스택은 tuple_contains + 문자열 비교 반복이었다. 크기 상한과 시간 제한을
# 함께 둔다 — 크기만으로는 '작지만 경로가 미친 SVG' 를 못 막는다.
MAX_SVG_BYTES = 2_000_000     # 2MB 초과는 로고로 보기 어렵다(지도·사진 트레이스)
RENDER_TIMEOUT = 25           # 초


def _render_worker(svg_text: str, out: str, width: int) -> None:
    import cairosvg, sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parent))
    # ⚠️ 이 스크립트는 자체 렌더러를 쓰느라 safesvg 의 정상화를 못 받고 있었다.
    #    그래서 Illustrator 엔티티(`&ns_svg;`)와 JS 가 남긴 `opacity="undefined"`,
    #    `rgb(65 74 71)` 같은 오작성에서 그대로 죽었다. 같은 전처리를 태운다.
    try:
        import safesvg
        data = safesvg.sanitize(safesvg.inline_internal_entities(svg_text.encode()))
    except Exception:
        data = svg_text.encode()
    cairosvg.svg2png(bytestring=data, write_to=out, output_width=width)


def render_png(svg: Path, out: Path) -> str | None:
    """성공하면 None, 실패하면 사유를 돌려준다."""
    import multiprocessing as mp
    from PIL import Image
    size = svg.stat().st_size
    if size > MAX_SVG_BYTES:
        return f"SVG 가 너무 큼 ({size/1024/1024:.1f}MB > {MAX_SVG_BYTES/1024/1024:.0f}MB)"
    try:
        text = prepare(svg.read_text(errors="replace"))
    except Exception as e:
        return f"{type(e).__name__}: {str(e)[:60]}"
    # 별도 프로세스로 돌려야 시간 초과 시 확실히 끊을 수 있다 —
    # 스레드로는 C 확장 안에서 도는 루프를 중단시킬 수 없다.
    ctx = mp.get_context("fork")
    proc = ctx.Process(target=_render_worker, args=(text, str(out), PNG_WIDTH))
    proc.start()
    proc.join(RENDER_TIMEOUT)
    if proc.is_alive():
        proc.terminate()
        proc.join(5)
        if proc.is_alive():
            proc.kill()
        out.unlink(missing_ok=True)
        return f"렌더 시간 초과 ({RENDER_TIMEOUT}초)"
    if proc.exitcode != 0 or not out.exists():
        out.unlink(missing_ok=True)
        return f"렌더 실패 (exit {proc.exitcode})"
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
        # 진행 표시가 없으면 멈춘 건지 도는 건지 알 수 없다.
        # 실제로 한 파일에 6시간 40분을 쓰면서도 아무도 몰랐다(2026-08-18).
        for _i, b in enumerate(brands, 1):
            if _i % 2000 == 0:
                print(f"   가짜벡터 검사 {_i:,}/{len(brands):,}", flush=True)
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

    for _i, b in enumerate(brands, 1):
        if _i % 1000 == 0:
            print(f"   PNG 생성 {_i:,}/{len(brands):,} (생성 {made:,})", flush=True)
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
            # ⚠️ svg-wanted.json 은 **최상위가 리스트**다. `w["brands"]` 로 읽으면
            #    TypeError 로 스크립트가 죽고, 이 단계가 실패하면서 뒤의
            #    파생물 생성·매니페스트·slim 재생성이 전부 skipped 된다.
            #    (2026-09-01 크론이 그렇게 죽었다)
            #    dict 로 감싼 형태도 있을 수 있어 둘 다 받는다.
            w = json.loads(WANTED.read_text())
            rows = w if isinstance(w, list) else w.get("brands", [])
            have = {x["id"] for x in rows if isinstance(x, dict) and "id" in x}
            new = [{"id": b["id"], "name_ko": b.get("name_ko"), "name_en": b.get("name_en"),
                    "category": b.get("category"), "domain": b.get("domain"),
                    "failed_source": "raster-wrapped-svg", "failed_at": time.strftime("%Y-%m-%d")}
                   for b in demoted if b["id"] not in have]
            if new:
                rows += new
                if isinstance(w, list):
                    out = rows
                else:
                    w["brands"] = rows
                    w["count"] = len(rows)
                    w["generated_at"] = time.strftime("%Y-%m-%d")
                    out = w
                WANTED.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")

    if not args.dry_run:
        # 일부 SVG는 CairoSVG가 지원하지 않는 문법을 쓴다. 이들은 개별 자산
        # 문제이지 전체 수집 실패가 아니다. 원인과 원본 해시를 남겨 다음 실행에서
        # 같은 파일을 다시 렌더링하느라 시간을 쓰지 않게 한다.
        report = []
        for item in failed:
            brand_id, reason = item.split(": ", 1)
            source = BASE / brand_id / "logo.svg"
            report.append({
                "id": brand_id,
                "reason": reason,
                "svg_sha256": hashlib.sha256(source.read_bytes()).hexdigest() if source.exists() else "",
                "recorded_at": time.strftime("%Y-%m-%d"),
            })
        FAILURES.write_text(json.dumps({
            "generated_at": time.strftime("%Y-%m-%d %H:%M"),
            "count": len(report),
            "brands": report,
            "note": "CairoSVG로 PNG를 만들 수 없는 개별 SVG 목록. SVG 원본이 바뀌면 재검토한다.",
        }, ensure_ascii=False, indent=1) + "\n")

    tag = "[dry-run] " if args.dry_run else ""
    print(f"{tag}logo.png 생성 {made}건 | 가짜 벡터 정리 {len(demoted)}건 | 실패 {len(failed)}건")
    for f in failed[:10]:
        print(f"   {f}")
    if demoted:
        print("   내림:", ", ".join((b.get("name_ko") or b["id"]) for b in demoted[:8]))
    # 실패 목록은 위 리포트로 관리한다. 유효하지 않은 단일 SVG가 전체 수집·배포를
    # 막으면 새 브랜드까지 CDN에 반영되지 않는다.
    return 0


if __name__ == "__main__":
    sys.exit(main())
