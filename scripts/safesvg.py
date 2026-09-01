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
import re
from pathlib import Path

MAX_SVG_BYTES = 2_000_000
RENDER_TIMEOUT = 25


class SvgRenderError(RuntimeError):
    """렌더를 포기했다. 사유가 메시지에 담긴다."""


_ENTITY = re.compile(rb"""<!ENTITY\s+([A-Za-z_][\w.-]*)\s+(?:"([^"]*)"|'([^']*)')\s*>""")
_DOCTYPE = re.compile(rb"<!DOCTYPE[^>[]*(?:\[[^\]]*\])?\s*>", re.S)


def inline_internal_entities(data: bytes) -> bytes:
    """Illustrator SVG 의 내부 엔티티를 값으로 펴고 DOCTYPE 을 지운다.

    cairosvg 는 defusedxml 로 파싱하는데, 그게 **모든** 엔티티 선언을
    거부한다(EntitiesForbidden). 그런데 Adobe Illustrator 가 내보낸 SVG 는
    거의 항상 이렇게 생겼다:

        <!DOCTYPE svg [ <!ENTITY ns_svg "http://www.w3.org/2000/svg"> ]>
        <svg xmlns="&ns_svg;">

    실제 위험(XXE)이 아니라 네임스페이스 별칭일 뿐인데 전부 렌더 실패했다 —
    2026-08-31 수집에서 **435건**이 이것 때문에 파생물을 못 만들었다.

    `unsafe=True` 로 푸는 건 답이 아니다. 그러면 외부 엔티티까지 열려
    신뢰할 수 없는 SVG(위키미디어·웹 수집분)에 XXE 를 허용하게 된다.
    **내부 선언만 값으로 치환하고 DOCTYPE 을 통째로 지운다** —
    SYSTEM/PUBLIC 을 가리키는 외부 엔티티는 값이 없으므로 자연히 빠진다.
    """
    if b"<!ENTITY" not in data[:4000]:
        return data
    head = data[:4000]
    ents = {m.group(1): (m.group(2) or m.group(3) or b"")
            for m in _ENTITY.finditer(head)}
    if not ents:
        return data
    body = _DOCTYPE.sub(b"", data, count=1)
    for name, val in ents.items():
        body = body.replace(b"&" + name + b";", val)
    return body


def _worker(src: str | bytes, out: str, width: int, transparent: bool) -> None:
    import cairosvg
    kw = {"write_to": out, "output_width": width,
          "background_color": None if transparent else "white"}
    if isinstance(src, str):
        src = Path(src).read_bytes()
    cairosvg.svg2png(bytestring=inline_internal_entities(src), **kw)


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
