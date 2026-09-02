#!/usr/bin/env python3
"""
브랜드 로고 변형 자동 생성

생성 파일:
  logo-800.png         SVG에서 직접 뽑은 800px 고해상도
  logo-icon.png        64×64px 아이콘 (파비콘/앱)
  logo-transparent.png 흰 배경 제거, 원본 색상 유지
  logo-white.png       투명 배경 + 흰색 (다크 배경 전용)

사용:
  python3 build-variants.py              # 전체 브랜드
  python3 build-variants.py --brand kia  # 특정 브랜드만
  python3 build-variants.py --dry-run    # 생성 없이 미리보기
"""

import argparse, colorsys, json, sys
from pathlib import Path
import cairosvg
from PIL import Image
import io

BASE = Path(__file__).parent / "_clients"
BRANDS_JSON = BASE / "brands.json"

# 심볼 분리는 logoform이 담당한다. 없어도 기존 동작으로 계속 돌아가야 하므로
# import 실패를 치명적으로 다루지 않는다.
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
try:
    import logoform
except ImportError:
    logoform = None

# cairosvg 렌더는 반드시 이걸 거친다 — 거대·병적 SVG 하나가 배치 전체를
# 멈추는 걸 막는다. 2026-08-18 에 ensure-logo-png 가 6시간 40분,
# 2026-08-19 에 이 파일이 3시간 3분을 한 파일에 날렸다.
import safesvg  # noqa: E402


def svg_to_pil(svg_path: Path, width: int) -> Image.Image:
    """SVG → PIL Image (지정 너비 기준, 비율 유지, 흰 배경)

    safesvg 를 거친다 — 크기·시간 가드가 걸리면 SvgRenderError 를 던지고,
    호출부(process_brand)가 그 브랜드만 실패로 기록하고 넘어간다.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
        tmp = Path(t.name)
    try:
        safesvg.render_to_file(svg_path, tmp, width)
        return Image.open(tmp).convert("RGBA")
    finally:
        tmp.unlink(missing_ok=True)


def svg_bytes_to_pil(svg_text: str, width: int) -> Image.Image:
    """메모리 SVG(심볼 크롭 결과)를 렌더한다. 파일과 같은 가드를 받는다."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
        tmp = Path(t.name)
    try:
        safesvg.render_to_file(svg_text, tmp, width, transparent=True)
        return Image.open(tmp).convert("RGBA")
    finally:
        tmp.unlink(missing_ok=True)


def png_to_pil(png_path: Path, width: int) -> Image.Image:
    """PNG → PIL Image (리사이즈)"""
    img = Image.open(png_path).convert("RGBA")
    ratio = width / img.width
    new_h = int(img.height * ratio)
    return img.resize((width, new_h), Image.LANCZOS)


def remove_white_bg(img: Image.Image, threshold: int = 235) -> Image.Image:
    """흰색/밝은 배경을 투명으로 변환"""
    result = img.copy()
    data = result.getdata()
    new_data = []
    for r, g, b, a in data:
        # 밝은 회색~흰색 영역을 투명 처리
        if r >= threshold and g >= threshold and b >= threshold:
            new_data.append((r, g, b, 0))
        else:
            new_data.append((r, g, b, a))
    result.putdata(new_data)
    return result


def is_monochrome(img: Image.Image, tol: int = 40) -> bool:
    """불투명 픽셀이 전부 검정 계열 아니면 흰색 계열인가 (회색 포함).

    컬러가 조금이라도 섞여 있으면 False. 이 판정으로 '통째로 반전해도 되는
    로고'와 '색을 지키면서 검은 부분만 바꿔야 하는 로고'를 가른다.
    """
    import numpy as np
    a = np.asarray(img.convert("RGBA"))
    m = a[..., 3] > 20
    if not m.any():
        return True
    rgb = a[..., :3][m].astype(int)
    chroma = rgb.max(1) - rgb.min(1)          # 채도 대용 — 0이면 무채색
    if (chroma > tol).mean() > 0.02:          # 유채색 픽셀이 2% 넘으면 컬러 로고
        return False
    lum = rgb.mean(1)
    mid = ((lum > 90) & (lum < 165)).mean()   # 중간 밝기 회색이 많으면 사진·그라데이션
    return mid < 0.25


def make_white_version(img: Image.Image) -> Image.Image:
    """다크 배경용 버전.

    예전엔 **불투명 픽셀을 전부 흰색으로** 칠했다. 그래서 색이 있는 로고가
    흰 덩어리가 되어 정체를 잃었다(국세청 태극·에이티즈 주황 등).

    규칙:
      · 흰/검(무채색) 로고 → 통째로 흰색으로 반전한다
      · 색이 있는 로고 → **색은 그대로 두고 어두운 부분만 흰색으로** 바꾼다
        (검정 배경에 얹었을 때 까맣게 묻히는 글씨만 살리는 것)
    """
    import numpy as np
    base = remove_white_bg(img)
    a = np.asarray(base.convert("RGBA")).copy()
    m = a[..., 3] > 20

    if is_monochrome(base):
        a[..., 0][m] = a[..., 1][m] = a[..., 2][m] = 255
        return Image.fromarray(a)

    rgb = a[..., :3].astype(int)
    lum = rgb.mean(2)
    chroma = rgb.max(2) - rgb.min(2)
    # 어둡고 무채색인 픽셀 = 검은 글씨·윤곽. 이것만 흰색으로 돌린다.
    dark = m & (lum < 110) & (chroma < 40)
    a[..., 0][dark] = a[..., 1][dark] = a[..., 2][dark] = 255
    return Image.fromarray(a)


def paint_white(img: Image.Image) -> Image.Image:
    """알파는 그대로 두고 색만 흰색으로. 이미 투명 배경인 이미지에 쓴다."""
    import numpy as np
    a = np.asarray(img.convert("RGBA")).copy()
    m = a[..., 3] > 20
    a[..., 0][m] = 255
    a[..., 1][m] = 255
    a[..., 2][m] = 255
    return Image.fromarray(a)


def choose_dark_variant(transparent_img: Image.Image) -> str:
    """로고 채도 분석 → 다크 배경에 투명(원색) vs 화이트 중 더 잘 보이는 버전 선택"""
    pixels = list(transparent_img.getdata())
    # 불투명 픽셀만 (배경 제외)
    logo_px = [(r, g, b) for r, g, b, a in pixels if a > 30]
    if not logo_px:
        return "white"

    # 흰색/밝은 픽셀 비율 체크 (원래 로고가 흰색이면 투명 버전이 안 보임)
    bright = sum(1 for r, g, b in logo_px if r > 220 and g > 220 and b > 220)
    if bright / len(logo_px) > 0.6:
        return "white"  # 대부분 흰색 → 화이트 버전 강제

    # 채도 평균 계산
    saturations = []
    for r, g, b in logo_px:
        _, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        saturations.append(s)
    avg_sat = sum(saturations) / len(saturations)

    # 채도 0.6 이상이면 강한 컬러 로고 → 투명(원색), 그 이하는 화이트가 더 임팩트
    return "transparent" if avg_sat >= 0.6 else "white"


def make_icon(img: Image.Image, size: int = 64) -> Image.Image:
    """정사각형 아이콘 크기로 리사이즈 (여백 추가해 비율 유지)"""
    base = remove_white_bg(img)
    base.thumbnail((size, size), Image.LANCZOS)
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - base.width) // 2
    y = (size - base.height) // 2
    icon.paste(base, (x, y), base)
    return icon


def svg_to_pil_alpha(svg_path: Path, width: int) -> Image.Image:
    """SVG → PIL Image. 배경을 깔지 않고 투명하게 렌더한다.

    흰 배경 위에 렌더하면 '흰색 로고'와 '배경'을 구분할 수 없다.
    실제로 그래서 sony·arsenal·railway 등 흰색 fill 로고 수백 개의
    파비콘이 remove_white_bg() 에 통째로 지워져 빈 파일이 돼 있었다.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
        tmp = Path(t.name)
    try:
        safesvg.render_to_file(svg_path, tmp, width, transparent=True)
        return Image.open(tmp).convert("RGBA")
    finally:
        tmp.unlink(missing_ok=True)


def _fit_icon(img: Image.Image, size: int) -> Image.Image:
    """이미 배경이 투명한 이미지를 정사각 아이콘에 맞춘다 (흰색 제거 안 함)."""
    base = img.crop(img.getbbox()) if img.getbbox() else img
    base.thumbnail((size, size), Image.LANCZOS)
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    icon.paste(base, ((size - base.width) // 2, (size - base.height) // 2), base)
    return icon


def _icon_from_image(img: Image.Image, size: int) -> Image.Image:
    """투명 렌더면 그대로 쓰고, 배경이 꽉 찬 렌더면 흰 배경을 제거한다.

    SVG 안에 흰 배경 사각형이 박혀 있는 경우가 있어서 투명 렌더라고
    항상 투명한 게 아니다. 알파가 사실상 전부 불투명하면 배경이 있다고 보고
    기존 remove_white_bg() 경로를 탄다.
    """
    import numpy as np

    a = np.asarray(img)
    opaque_ratio = float((a[..., 3] > 25).mean()) if a.size else 1.0
    # ⚠️ 흰 로고에 make_icon(=흰 배경 제거)을 태우면 로고가 통째로 지워져
    #    파비콘이 빈 파일이 된다(2026-09-02 니어스랩·송우인포텍·세미티에스).
    #    잉크가 사실상 전부 순백이면 배경 제거를 건너뛴다.
    if a.size:
        op = a[..., 3] > 25
        if op.any() and float((a[..., :3][op].mean(1) > 240).mean()) > 0.97:
            return _fit_icon(img, size)
    if opaque_ratio > 0.97:          # 투명한 데가 거의 없다 = 배경이 깔려 있다
        return make_icon(img, size)
    return _fit_icon(img, size)


def build_icon(svg_path: Path, png_path: Path, size: int = 64):
    """파비콘 생성. 가로형 로고는 심볼만 떼어내야 판독이 된다.

    기존 make_icon()은 가로로 긴 로크업을 통째로 64x64에 욱여넣어서
    가로형·워드마크형(전체의 약 37%)의 파비콘이 판독 불가였다.

    체인 (실패하면 다음으로, 마지막은 항상 기존 동작):
      1. logoform이 심볼을 분리해내면 그 심볼로 만든다
      2. 안 되면 전체 로고로 만든다 — 저신뢰 크롭으로는 절대 떨어지지 않는다

    두 경로 모두 투명 렌더를 쓴다 (흰색 로고가 지워지는 문제 때문에).

    반환: (이미지, 방식) — 방식은 "symbol" 또는 "whole"
    """
    # 1) 사람이 확인해 등록한 심볼이 있으면 그게 최우선이다.
    #    (variants.override.json 으로 넣은 것 — 자동 분리보다 정확하다)
    manual_symbol = svg_path.parent / "variants" / "symbol.svg"
    if manual_symbol.exists():
        try:
            img = _icon_from_image(svg_to_pil_alpha(manual_symbol, size * 4), size)
            if img.getbbox() is not None:
                return img, "symbol"
        except Exception:
            pass

    if svg_path.exists() and logoform is not None:
        try:
            arr = logoform.render(svg_path, 900)
            if arr is not None:
                # 세로 분리는 자동으로 쓰지 않는다 — logoform 문서의
                # '세로 분리를 자동으로 쓰지 않는 이유' 참조
                split = logoform.find_symbol_split(arr, 900)
                if split is not None:
                    cropped = logoform.crop_viewbox(
                        svg_path.read_text(errors="ignore"),
                        split,
                        (arr.shape[1], arr.shape[0]),
                    )
                    if cropped:
                        sym = svg_bytes_to_pil(cropped, size * 4)
                        return _icon_from_image(sym, size), "symbol"
        except Exception:
            pass  # 어떤 이유로든 실패하면 조용히 전체 로고 경로로

    if svg_path.exists():
        try:
            icon = _icon_from_image(svg_to_pil_alpha(svg_path, 256), size)
        except Exception:
            icon = None
        # SVG 안에 래스터가 내장돼 있으면(xlink:href) cairosvg가 빈 이미지를 뱉는다.
        # 그 결과를 그대로 저장하면 파비콘이 투명한 빈 파일이 된다 → PNG로 간다.
        if icon is not None and icon.getbbox() is not None:
            return icon, "whole"

    if png_path.exists():
        # ⚠️ make_icon 을 직접 부르면 흰 배경 제거가 무조건 돌아 **흰 로고가
        #    통째로 지워진다**. _icon_from_image 가 순백 로고를 알아보므로
        #    반드시 그것을 거친다(2026-09-02 니어스랩·송우인포텍·세미티에스).
        return _icon_from_image(png_to_pil(png_path, 256), size), "whole"
    # 원본이 아예 없다 — 빈 아이콘을 만들어 덮어쓰지 않는다
    raise ValueError("아이콘을 만들 원본이 없음 (logo.svg 렌더 실패 + logo.png 없음)")


def process_brand(brand: dict, dry_run: bool = False) -> dict:
    brand_id = brand["id"]
    brand_dir = BASE / brand_id
    name = brand["name_ko"]

    svg_path = brand_dir / "logo.svg"
    png_path = brand_dir / "logo.png"

    results = {"brand": brand_id, "name": name, "created": [], "skipped": [], "errors": []}

    if not svg_path.exists() and not png_path.exists():
        results["errors"].append("logo.svg 도 logo.png 도 없음")
        return results

    # 밝은(흰색) 로고는 흰 배경에 렌더하면 배경과 구분이 안 돼서
    # remove_white_bg() 에 통째로 지워진다. 실제로 sony·unity·capgemini 등
    # 82개의 logo-800/transparent/white 가 백지이거나 빈 파일이 돼 있었다.
    # 그런 브랜드는 처음부터 투명 렌더를 쓴다 (brands.json 의 light_logo).
    is_light = bool(brand.get("light_logo"))

    # ⚠️ light_logo 는 별도 스크립트(scan-light-logos)가 붙인다. 신규 수집분은
    #    그게 아직 안 돌아 플래그가 없다. 그 사이에 파생물을 만들면
    #    logo-white·logo-icon 이 빈 파일이 된다(2026-09-02 신규 21건 중 3건).
    #    **불투명 잉크가 전부 순백이면** 그 자리에서 밝은 로고로 본다 —
    #    판정기를 기다릴 필요가 없는 명백한 경우다.
    if not is_light and png_path.exists():
        try:
            import numpy as _np
            _a = _np.array(Image.open(png_path).convert("RGBA"))
            _op = _a[..., 3] > 40
            if _op.any() and float((_a[..., :3][_op].mean(1) > 240).mean()) > 0.97:
                is_light = True
        except Exception:
            pass

    def _safe_remove_white(img):
        """배경 제거 결과가 비면 원본을 돌려준다.

        흰색 로고는 '흰색이 곧 잉크'라 remove_white_bg 가 전부 지운다.
        light_logo 판정이 아직 없는 신규 브랜드가 여기로 샌다."""
        out = remove_white_bg(img)
        try:
            import numpy as _np
            if (_np.array(out.convert("RGBA"))[..., 3] > 24).mean() < 0.005:
                return img
        except Exception:
            pass
        return out

    def get_source_img(width):
        if svg_path.exists():
            return svg_to_pil_alpha(svg_path, width) if is_light else svg_to_pil(svg_path, width)
        else:
            return png_to_pil(png_path, width)

    icon_method = {"how": None}

    def _icon():
        img, how = build_icon(svg_path, png_path, 64)
        icon_method["how"] = how
        return img

    targets = {
        # ⚠️ 예전엔 SVG 가 있을 때만 만들었다. 그래서 **PNG 만 있는 브랜드는
        #    logo-800 이 영영 없었고**, 상세 페이지의 'PNG 800px' 카드가 404 였다.
        #    (2026-09-02 상장사 신규 21건 중 10건이 그랬다)
        #    원본이 800보다 작으면 확대하지 않고 원본 크기로 둔다 — 억지로
        #    키우면 뭉갠 이미지가 고해상도로 둔갑한다.
        "logo-800.png": lambda: get_source_img(800),
        "logo-icon.png": _icon,
        # 밝은 로고는 이미 투명 렌더라 remove_white_bg() 를 태우면 로고 자체가
        # 지워진다 (흰색이 곧 잉크이기 때문). 그대로 쓰고, 화이트 버전은
        # 알파를 유지한 채 색만 흰색으로 칠한다.
        # ⚠️ light_logo 플래그에만 기대면 **아직 판정 안 된 신규 브랜드**가 샌다.
        #    흰 로고에 remove_white_bg 를 태우면 로고 자체가 지워져 빈 파일이
        #    된다(2026-09-02 신규 21건 중 3건). 결과가 비면 원본으로 되돌린다.
        "logo-transparent.png": (lambda: get_source_img(400)) if is_light
                                 else (lambda: _safe_remove_white(get_source_img(400))),
        "logo-white.png": (lambda: paint_white(get_source_img(400))) if is_light
                           else (lambda: make_white_version(get_source_img(400))),
    }

    transparent_img = None  # 채도 분석용 캐시

    for filename, builder in targets.items():
        out_path = brand_dir / filename
        if out_path.exists():
            results["skipped"].append(filename)
            # 기존 logo-transparent.png로 채도 분석 — dark_variant 를 정하기 위해서다.
            # ⚠️ 이미 dark_variant 가 있으면 열지 않는다. 예전엔 4종이 전부
            #    있어서 건너뛰는 브랜드도 이 400px PNG 를 매번 열었고, 4만 개를
            #    다 열다 보니 이 단계가 **54분(전체의 20%)** 이었다.
            #    99%가 이미 값을 갖고 있어 대부분 열 필요가 없다.
            if (filename == "logo-transparent.png"
                    and not brand.get("dark_variant")):
                try:
                    transparent_img = Image.open(out_path).convert("RGBA")
                except Exception:
                    pass
            continue

        if dry_run:
            if filename == "logo-800.png" and not svg_path.exists():
                results["skipped"].append(f"{filename} (SVG 없음)")
            else:
                results["created"].append(f"{filename} [DRY RUN]")
            continue

        try:
            img = builder()
            if img is None:
                results["skipped"].append(f"{filename} (SVG 없음)")
                continue
            img.save(out_path, "PNG", optimize=True)
            results["created"].append(filename)
            if filename == "logo-transparent.png":
                transparent_img = img
        except Exception as e:
            results["errors"].append(f"{filename}: {e}")

    # 다크 프리뷰 variant 결정 → brand 딕셔너리에 기록
    if transparent_img is not None and not dry_run:
        results["dark_variant"] = choose_dark_variant(transparent_img)

    results["icon_method"] = icon_method["how"]
    return results


def _process_one(arg):
    """ProcessPoolExecutor 워커. 브랜드 하나를 처리하고 결과 dict 를 돌려준다.

    한 브랜드가 죽어도 배치는 계속 간다 — 예외를 결과로 바꿔 돌려준다.
    """
    brand, dry_run = arg
    try:
        return process_brand(brand, dry_run=dry_run)
    except Exception as e:  # noqa: BLE001
        return {"brand": brand["id"], "name": brand.get("name_ko") or brand["id"],
                "created": [], "skipped": [], "errors": [f"{type(e).__name__}: {e}"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", help="특정 브랜드 ID만")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="기존 파일도 덮어쓰기")
    parser.add_argument("--force-icon", action="store_true",
                        help="logo-icon.png만 재생성 (나머지 변형은 보존)")
    parser.add_argument("--report", help="심볼/통짜 판정 결과를 JSON으로 저장할 경로")
    # 브랜드 4만 개 × 변형 4종을 단일 프로세스로 돌리면 분당 77개, 약 5시간이다
    # (실측 2026-08-19, 코어 10개 중 1개만 사용). process_brand 는 브랜드마다
    # 독립적이고 brands.json 쓰기는 루프가 끝난 뒤 한 번만 하므로 병렬화가 안전하다.
    parser.add_argument("--jobs", type=int, default=1,
                        help="동시 처리 프로세스 수 (기본 1, 권장 코어수-2)")
    args = parser.parse_args()

    brands = json.loads(BRANDS_JSON.read_text())["brands"]
    if args.brand:
        brands = [b for b in brands if b["id"] == args.brand]
        if not brands:
            print(f"❌ 브랜드 '{args.brand}' 없음")
            sys.exit(1)

    if args.force or args.force_icon:
        # --force 는 변형 4종 전부, --force-icon 은 파비콘만 지우고 재생성한다.
        # 파비콘 로직만 바뀌었을 때 나머지 3종까지 다시 만들 이유가 없다.
        wipe = (["logo-icon.png"] if args.force_icon and not args.force
                else ["logo-800.png", "logo-icon.png", "logo-transparent.png", "logo-white.png"])
        for brand in brands:
            d = BASE / brand["id"]
            for f in wipe:
                p = d / f
                if p.exists():
                    p.unlink()

    all_brands_data = json.loads(BRANDS_JSON.read_text())
    dark_updates: dict[str, str] = {}
    brand_map = {b["id"]: b for b in all_brands_data["brands"]}
    updated = 0
    total_created = 0
    icon_stats = {"symbol": [], "whole": []}

    def _emit(r):
        """한 브랜드 결과를 집계·출력한다. 순차·병렬 양쪽에서 같은 코드를 쓴다."""
        nonlocal updated, total_created
        if r.get("icon_method"):
            icon_stats[r["icon_method"]].append(r["brand"])
        status = []
        if r["created"]:
            status.append(f"✅ {', '.join(r['created'])}")
            total_created += len(r["created"])
        if r["skipped"]:
            status.append(f"⏭  {', '.join(r['skipped'])}")
        if r["errors"]:
            status.append(f"❌ {', '.join(r['errors'])}")

        # dark_variant brands.json 업데이트
        if "dark_variant" in r and not args.dry_run:
            bid = r["brand"]
            if bid in brand_map and brand_map[bid].get("dark_variant") != r["dark_variant"]:
                brand_map[bid]["dark_variant"] = r["dark_variant"]
                dark_updates[bid] = r["dark_variant"]
                updated += 1
                status.append(f"🎨 dark={r['dark_variant']}")

        print(f"[{r['name']}] {' | '.join(status) if status else '변경 없음'}", flush=True)

    if args.jobs > 1 and not args.brand:
        # fork 로 자식에서 렌더하고 결과 dict 만 돌려받는다. 파일 쓰기는
        # 브랜드 폴더별로 갈라져 충돌하지 않고, brands.json 은 부모만 쓴다.
        from concurrent.futures import ProcessPoolExecutor
        import multiprocessing as _mp
        ctx = _mp.get_context("fork")
        with ProcessPoolExecutor(max_workers=args.jobs, mp_context=ctx) as ex:
            for r in ex.map(_process_one, [(b, args.dry_run) for b in brands], chunksize=8):
                if r is not None:
                    _emit(r)
    else:
        for brand in brands:
            _emit(process_brand(brand, dry_run=args.dry_run))

    if updated and not args.dry_run:
        # ⚠️ 통째로 쓰면 수집기와 겹쳐 파일이 깨진다(2026-09-02 두 번).
        #    임시 파일에 쓰고 검증한 뒤 os.replace 로 갈아 끼운다.
        # ⚠️⚠️ 원자적 쓰기만으로는 부족하다. 이 함수는 시작할 때 읽은
        #    스냅샷을 **20분 뒤에** 쓴다. 그 사이의 변경이 통째로 사라진다.
        #    2026-09-03 에 숨김 처리 4건이 지워지고 신규 브랜드 1건이
        #    레코드째 사라졌다. 파일은 멀쩡해서 에러도 안 났다.
        #    → 저장 직전에 **락을 잡고 다시 읽어** dark_variant 만 얹는다.
        sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
        import atomic_json
        with atomic_json.locked(BRANDS_JSON):
            fresh = json.loads(BRANDS_JSON.read_text())
            fm = {b["id"]: b for b in fresh["brands"]}
            for bid, v in dark_updates.items():
                if bid in fm:
                    fm[bid]["dark_variant"] = v
            fresh["total"] = len(fresh["brands"])
            atomic_json.write_json(BRANDS_JSON, fresh, indent=2, separators=None)
        print(f"\n📝 brands.json dark_variant 업데이트: {updated}개")

    print(f"\n완료: {total_created}개 파일 생성")

    n_sym, n_whole = len(icon_stats["symbol"]), len(icon_stats["whole"])
    if n_sym or n_whole:
        print(f"파비콘: 심볼 분리 {n_sym}개 / 통짜 {n_whole}개")
    if args.report:
        Path(args.report).write_text(
            json.dumps(icon_stats, ensure_ascii=False, indent=2)
        )
        print(f"📝 판정 리포트: {args.report}")


if __name__ == "__main__":
    main()
