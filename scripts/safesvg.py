#!/usr/bin/env python3
"""cairosvg 렌더를 안전하게 감싼다 — 한 파일이 배치 전체를 멈추지 못하게.

왜 공용 모듈인가 (2026-08-18~19):
  같은 함정을 **두 번** 밟았다.
    ① ensure-logo-png.py — 거대 SVG 하나에 6시간 40분 (CPU 97%, 산출물 0)
    ② build-variants.py  — 거기에 가드를 안 넣어 3시간 3분을 또 날렸다
  cairosvg 는 복잡한 SVG 를 파싱할 때 이차 시간 복잡도에 빠진다
  (스택: tuple_contains + PyUnicode_RichCompare 무한 반복).
  프로세스는 살아 있고 CPU 는 100% 라 "바쁘게 도는 것"처럼 보이는 게 위험하다.

두 겹으로 막는다:
  · 크기 상한 — 로고가 2MB 를 넘을 이유가 없다(지도·사진 트레이스다)
  · 시간 제한 — 크기만으론 '작지만 경로가 미친 SVG' 를 못 막는다
시간 제한은 **별도 프로세스**로만 가능하다. 스레드로는 C 확장 안에서
도는 루프를 중단시킬 수 없다.
"""
from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

MAX_SVG_BYTES = 2_000_000
RENDER_TIMEOUT = 25


class SvgRenderError(RuntimeError):
    """렌더를 포기했다. 사유가 메시지에 담긴다."""


def _worker(src: str | bytes, out: str, width: int, transparent: bool) -> None:
    import cairosvg
    kw = {"write_to": out, "output_width": width,
          "background_color": None if transparent else "white"}
    if isinstance(src, bytes):
        cairosvg.svg2png(bytestring=src, **kw)
    else:
        cairosvg.svg2png(url=src, **kw)


def render_to_file(svg: Path | bytes | str, out: Path, width: int, *,
                   transparent: bool = False) -> None:
    """실패하면 SvgRenderError 를 던진다 — 조용히 빈 결과를 돌려주지 않는다.

    svg 는 파일 경로(Path) 또는 SVG 원문(bytes/str) 둘 다 받는다.
    메모리 SVG 도 같은 가드를 받아야 한다 — 심볼 크롭 결과처럼 파일이 아닌
    경로에서도 병적 SVG 가 나올 수 있다.
    """
    if isinstance(svg, Path):
        size = svg.stat().st_size
        src: str | bytes = str(svg)
    else:
        src = svg.encode() if isinstance(svg, str) else svg
        size = len(src)
    if size > MAX_SVG_BYTES:
        raise SvgRenderError(
            f"SVG 가 너무 큼 ({size/1024/1024:.1f}MB > {MAX_SVG_BYTES/1024/1024:.0f}MB)")
    ctx = mp.get_context("fork")
    proc = ctx.Process(target=_worker, args=(src, str(out), width, transparent))
    proc.start()
    proc.join(RENDER_TIMEOUT)
    if proc.is_alive():
        proc.terminate()
        proc.join(5)
        if proc.is_alive():
            proc.kill()
        out.unlink(missing_ok=True)
        raise SvgRenderError(f"렌더 시간 초과 ({RENDER_TIMEOUT}초)")
    if proc.exitcode != 0 or not out.exists():
        out.unlink(missing_ok=True)
        raise SvgRenderError(f"렌더 실패 (exit {proc.exitcode})")
