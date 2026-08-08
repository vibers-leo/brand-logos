#!/usr/bin/env python3
"""
logoform — 로고 형태 분석·심볼 분리 라이브러리

순수 라이브러리다. 파일을 쓰지 않고, 인자로 받은 것만 본다.
호출부: build-variants.py(파비콘), scripts/build-logo-variants.py(매니페스트),
        scripts/check-assets.py(검증)

핵심 개념
---------
로고는 종횡비로 네 형태로 갈린다. 가로형·워드마크형은 64x64 파비콘에 그대로
넣으면 판독이 불가능하므로, 심볼 부분만 떼어내야 한다.

심볼 분리는 **래스터로 위치를 찾고 벡터로 자른다**:
  1) SVG를 렌더해서 잉크가 있는 열(column) 프로파일을 만든다
  2) 글리프 덩어리 사이 최대 공백을 찾는다
  3) 그 지점이 '글자 사이'가 아니라 '심볼과 워드마크 사이'인지 게이트로 검증
  4) 통과하면 픽셀좌표를 viewBox 단위로 환산해 viewBox 속성만 교체

viewBox만 바꾸므로 path는 하나도 건드리지 않는다 = 무손실이고 되돌릴 수 있다.

게이트 임계값과 그 근거 (2026-08-07 실측으로 확정)
------------------------------------------------
  GAP_RATIO_MIN = 1.8   최대공백 / 나머지공백중앙값.
                        글자 사이 간격은 서로 비슷하지만 심볼-워드마크 사이는
                        확연히 넓다. 이 비율이 'coupang'을 c/oupang으로 자르는
                        사고를 막는 핵심 방어선이다.
  PIECE_AR_MIN/MAX = 0.6 / 1.6
                        심볼은 대체로 정사각형에 가깝다. 'OLIVE'(3:1)처럼
                        가로로 긴 조각은 글자 뭉치이지 심볼이 아니다.
  PIECE_W_MIN/MAX = 0.12 / 0.45
                        심볼이 전체 폭의 절반을 넘으면 그건 워드마크가 아니라
                        이미 심볼 위주 로고다. 12% 미만이면 장식 요소다.
  PIECE_SEG_MAX = 1     심볼은 붙어 있는 한 덩어리다. 글자 뭉치는 여러 덩어리다.
                        이게 없으면 'Gmarket'의 오른쪽을 'rket'(4덩어리)으로
                        자르는 사고가 난다 — 폭·종횡비 조건은 통과해버리기 때문에
                        이 규칙이 유일한 방어선이다.
                        처음엔 2까지 허용했다(점·악센트가 분리된 심볼 때문에).
                        실측해보니 2덩어리 24건 중 10건이 글자 조각이었다
                        — airbus→'AI', turborepo→'TU', versace→'VE', sanofi→'sa'.
                        '조각과 나머지의 글자 폭 리듬이 비슷하면 글자'라는 규칙도
                        시험했으나 24건 중 8건을 틀려서 폐기했다.
                        1로 조이면 회수를 5.6% 잃는 대신(429→405) 글자 조각이
                        전부 사라진다. 잘못된 파비콘이 못생긴 파비콘보다 나쁘므로
                        정밀도를 택한다.
  REST_SEG_MIN = 3      심볼을 뗀 나머지가 '단어'처럼 보여야 한다.
                        'arm'을 a|rm 으로 자르면 나머지가 2덩어리뿐이다. 진짜
                        로크업이라면 나머지는 글자 여러 개다. 이 규칙이 짧은
                        워드마크를 글자 단위로 쪼개는 사고를 막는다.
                        4로 올리는 것도 재봤다: 회수가 11% 줄고(70→62건) 대신
                        'REWE'→'R' 같은 4글자 워드마크 케이스가 걸러진다. 그런데
                        그건 브랜드 이니셜이라 무해한 반면, 유해한 오분리
                        (arm→'a', Gmarket→'rket')는 3에서 이미 전부 막힌다.
                        측정해보고 3을 택했다 — 짐작이 아니다.

심볼은 왼쪽만 본다
------------------
오른쪽 조각도 시도해봤으나 700개 표본에서 우측 판정 3건이 **전부 오분리**였다
(kth→'h', eyeem→'Em', behance→'ē'). 좌측은 15건 중 14건이 정확했다.
실무에서 로크업은 거의 항상 심볼이 왼쪽이고, 우측 판정은 워드마크의 마지막
글자를 집는 실패로 이어진다. 회수를 조금 잃더라도 우측 시도는 하지 않는다.

지배 원칙: **애매하면 자르지 말고 수동으로 넘긴다.**
잘못 자른 파비콘은 못생긴 파비콘보다 나쁘다. 회수 손해를 감수하고 정밀도를 택한다.
이 규칙을 모르는 사람이 게이트를 느슨하게 풀면 워드마크가 조용히 뭉개진다.

검증 결과 (400개 표본):
  이미 심볼형 61% / 자동분리 가능 7% / 워드마크·애매 13% / 통짜 17%
  게이트가 정확히 거부: coupang, Gmarket, OLIVE YOUNG, NAVER (전부 심볼 없음)
  게이트가 정확히 통과: kakaobank (진짜 심볼+워드마크)
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# ── 알고리즘 버전 ────────────────────────────────────────────────────────────
# 분류·크롭 결과에 영향을 주는 변경을 하면 반드시 올린다.
# 매니페스트의 algo_v 와 비교해 재생성 여부를 판단하므로, 올리면 전량 재계산된다.
ALGO_V = 1

# ── 임계값 (위 docstring의 근거 참조) ────────────────────────────────────────
GAP_RATIO_MIN = 1.8
PIECE_AR_MIN, PIECE_AR_MAX = 0.6, 1.6
PIECE_W_MIN, PIECE_W_MAX = 0.12, 0.45
PIECE_SEG_MAX = 1
REST_SEG_MIN = 3

# 형태 분류 경계 (종횡비 = 폭/높이)
AR_VERTICAL_MAX = 0.8
AR_SYMBOL_MAX = 1.25
AR_HORIZONTAL_MAX = 3.0

# 분리를 시도할 최소 종횡비. 이보다 정사각형에 가까우면 이미 심볼이다.
AR_SPLIT_MIN = 1.3

# 렌더가 사실상 비었는지 판단하는 기준.
# cairosvg는 필터·내장 래스터가 있는 SVG를 조용히 빈 이미지로 렌더한다.
# 그 노이즈를 분석하면 엉뚱한 좌표가 나오므로 아예 건너뛴다.
INK_RATIO_MIN = 0.005
# 전면이 잉크면(배경 사각형 등) 열 프로파일에 공백이 없어 분석이 무의미하다.
INK_RATIO_MAX = 0.95

ALPHA_MIN = 25          # 이 이하 알파는 배경으로 본다
NEAR_WHITE = 235        # 이 이상 밝고 무채색이면 배경으로 본다
CHROMA_MIN = 25         # RGB 최대-최소 차이가 이 이상이면 유채색 = 잉크


@dataclass(frozen=True)
class Split:
    """심볼 분리 결과. 픽셀 좌표계 기준."""
    x0: int              # 심볼 조각 좌측 끝
    x1: int              # 심볼 조각 우측 끝 (포함)
    y0: int
    y1: int
    side: str            # "left" | "right" — 심볼이 어느 쪽이었나
    confidence: float
    render_width: int    # x0/x1 이 어느 렌더 폭 기준인지


def _svg_bytes(path: Path) -> bytes | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    head = raw[:512].lower()
    if b"<!doctype html" in head or head.lstrip()[:5].startswith(b"<html"):
        return None            # 404 HTML이 .svg로 저장된 사고 (2026-08-07 참조)
    if b"<svg" not in raw[:2048].lower() and not raw.lstrip().startswith(b"<?xml"):
        return None
    return raw


def render(path: Path, width: int = 1200) -> np.ndarray | None:
    """SVG/PNG → RGBA ndarray. 렌더가 비었거나 꽉 찼으면 None (분석 불가)."""
    import cairosvg
    from PIL import Image

    p = Path(path)
    try:
        if p.suffix.lower() == ".svg":
            if _svg_bytes(p) is None:
                return None
            raw = cairosvg.svg2png(url=str(p), output_width=width)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        else:
            img = Image.open(p).convert("RGBA")
            if img.width != width:
                h = max(1, round(img.height * width / img.width))
                img = img.resize((width, h), Image.LANCZOS)
    except Exception:
        return None

    arr = np.asarray(img)
    m = ink_mask(arr)
    ratio = float(m.mean()) if m.size else 0.0
    if not (INK_RATIO_MIN <= ratio <= INK_RATIO_MAX):
        return None
    return arr


def ink_mask(arr: np.ndarray) -> np.ndarray:
    """실제 로고 픽셀 마스크.

    배경이 어떻게 표현돼 있느냐에 따라 판정이 달라진다:

    - 투명한 영역이 있으면 → **알파가 곧 잉크다.** 색은 보지 않는다.
      흰색 fill 로고(sony·arsenal·railway 등 수백 개)를 색으로 판정하면
      배경과 구분이 안 돼서 '잉크 없음'이 되고, 분석에서 통째로 빠진다.
    - 전면이 불투명하면 → SVG에 배경 사각형이 박혀 있는 경우다.
      이때만 '유채색이거나 어두운' 픽셀을 잉크로 본다.
    """
    a = arr.astype(np.int16)
    alpha = a[..., 3]
    opaque = alpha > ALPHA_MIN
    if opaque.size and float(opaque.mean()) <= 0.97:
        return opaque
    rgb = a[..., :3]
    chromatic = (rgb.max(2) - rgb.min(2)) > CHROMA_MIN
    dark = rgb.max(2) < NEAR_WHITE
    return opaque & (chromatic | dark)


def ink_ratio(arr: np.ndarray) -> float:
    m = ink_mask(arr)
    return float(m.mean()) if m.size else 0.0


def bbox(arr: np.ndarray) -> tuple[int, int, int, int] | None:
    """잉크의 바운딩박스 (x0, y0, x1, y1). 잉크가 없으면 None."""
    m = ink_mask(arr)
    cols, rows = m.any(0), m.any(1)
    if not cols.any() or not rows.any():
        return None
    xs, ys = np.where(cols)[0], np.where(rows)[0]
    return int(xs[0]), int(ys[0]), int(xs[-1]), int(ys[-1])


def aspect(arr: np.ndarray) -> float | None:
    """잉크 영역의 종횡비. 캔버스 여백이 아니라 실제 로고 기준으로 잰다."""
    b = bbox(arr)
    if b is None:
        return None
    x0, y0, x1, y1 = b
    h = y1 - y0 + 1
    return (x1 - x0 + 1) / h if h else None


def _segments(cols: np.ndarray, x0: int, x1: int) -> list[tuple[int, int]]:
    """잉크가 연속으로 있는 구간 = 글리프 덩어리."""
    out: list[tuple[int, int]] = []
    start: int | None = None
    for x in range(x0, x1 + 2):
        on = x <= x1 and bool(cols[x])
        if on and start is None:
            start = x
        elif not on and start is not None:
            out.append((start, x - 1))
            start = None
    return out


def _try_left(segs, gaps, x0, x1, y0, y1, render_width) -> Split | None:
    """왼쪽 조각이 심볼로서 게이트를 통과하는지 검사."""
    W, H = x1 - x0 + 1, y1 - y0 + 1
    if H <= 0 or W <= 0 or not gaps:
        return None

    ordered = sorted(gaps, key=lambda g: -g[0])
    biggest, cut = ordered[0]
    others = [g for g, _ in ordered[1:]]
    median = float(np.median(others)) if others else 0.0
    ratio = biggest / median if median > 0 else float("inf")
    if ratio < GAP_RATIO_MIN:
        return None

    px0, px1 = x0, cut
    pw = px1 - px0 + 1
    if not (PIECE_AR_MIN <= pw / H <= PIECE_AR_MAX):
        return None
    if not (PIECE_W_MIN <= pw / W <= PIECE_W_MAX):
        return None

    # 조각이 몇 덩어리인가 — 심볼은 붙어 있고, 글자 뭉치는 흩어져 있다.
    # 폭·종횡비만으로는 'Gmarket' → 'rket' 같은 오분리를 못 막는다.
    piece_segs = sum(1 for s, e in segs if s >= px0 and e <= px1)
    if piece_segs > PIECE_SEG_MAX:
        return None

    # 나머지가 '단어'처럼 보이는가 — 'arm'을 a|rm 으로 자르는 것을 막는다.
    if len(segs) - piece_segs < REST_SEG_MIN:
        return None

    # 공백이 압도적일수록 신뢰도가 높다. 4배를 상한으로 0.5~1.0에 매핑.
    confidence = round(min(1.0, 0.5 + min(ratio, 4.0) / 8.0), 3)
    return Split(px0, px1, y0, y1, "left", confidence, render_width)


def find_symbol_split(arr: np.ndarray, render_width: int | None = None) -> Split | None:
    """심볼 조각을 찾는다. 왼쪽만 본다 (모듈 docstring의 '심볼은 왼쪽만 본다' 참조)."""
    b = bbox(arr)
    if b is None:
        return None
    x0, y0, x1, y1 = b
    H = y1 - y0 + 1
    if H <= 0 or (x1 - x0 + 1) / H < AR_SPLIT_MIN:
        return None            # 이미 정사각형에 가까움 = 분리할 게 없다

    cols = ink_mask(arr).any(0)
    segs = _segments(cols, x0, x1)
    if len(segs) < 2:
        return None            # 통짜 = 분리 불가

    gaps = [(segs[i + 1][0] - segs[i][1] - 1, segs[i][1]) for i in range(len(segs) - 1)]
    rw = render_width if render_width is not None else int(arr.shape[1])

    return _try_left(segs, gaps, x0, x1, y0, y1, rw)


def classify(ar: float | None) -> str:
    """종횡비 → 형태. arr 가 아니라 이미 잰 종횡비를 받는다."""
    if ar is None:
        return "unknown"
    if ar < AR_VERTICAL_MAX:
        return "vertical"
    if ar <= AR_SYMBOL_MAX:
        return "symbol"
    if ar <= AR_HORIZONTAL_MAX:
        return "horizontal"
    return "wordmark"


_VIEWBOX_RE = re.compile(r'viewBox\s*=\s*["\']([-\d.eE\s,]+)["\']')
_WH_RE = re.compile(r'\s(?:width|height)\s*=\s*["\'][^"\']*["\']')


def read_viewbox(svg_text: str) -> list[float] | None:
    m = _VIEWBOX_RE.search(svg_text)
    if not m:
        return None
    try:
        v = [float(x) for x in m.group(1).replace(",", " ").split()]
    except ValueError:
        return None
    return v if len(v) == 4 and v[2] > 0 and v[3] > 0 else None


def crop_viewbox(svg_text: str, split: Split, render_size: tuple[int, int]) -> str | None:
    """viewBox 속성만 교체해 심볼 영역으로 자른 SVG 텍스트를 만든다.

    path·fill·transform 등은 하나도 건드리지 않는다. 브라우저가 viewport 밖을
    잘라주므로 시각적으로는 크롭이고, 원본 정보는 파일 안에 그대로 남는다.
    width/height 는 제거해서 부모 크기를 따르게 한다.
    """
    vb = read_viewbox(svg_text)
    if vb is None:
        return None            # viewBox 없는 SVG는 좌표 환산 근거가 없다
    rw, rh = render_size
    if rw <= 0 or rh <= 0:
        return None

    sx, sy = vb[2] / rw, vb[3] / rh
    nx = vb[0] + split.x0 * sx
    ny = vb[1] + split.y0 * sy
    nw = (split.x1 - split.x0 + 1) * sx
    nh = (split.y1 - split.y0 + 1) * sy
    if nw <= 0 or nh <= 0:
        return None

    out = _VIEWBOX_RE.sub(
        f'viewBox="{nx:.4f} {ny:.4f} {nw:.4f} {nh:.4f}"', svg_text, count=1
    )
    # 루트 <svg ...> 안의 width/height 만 지운다 (자식 요소는 건드리면 안 됨)
    m = re.search(r"<svg\b[^>]*>", out, re.IGNORECASE)
    if m:
        head = _WH_RE.sub("", m.group(0))
        out = out[: m.start()] + head + out[m.end():]
    return out


def analyze(path: Path, width: int = 1200):
    """한 파일에 대한 (형태, 종횡비, 분리결과). 분석 불가면 (unknown, None, None)."""
    arr = render(path, width)
    if arr is None:
        return "unknown", None, None
    ar = aspect(arr)
    return classify(ar), ar, find_symbol_split(arr, width)
