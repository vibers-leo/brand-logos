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


def svg_to_pil(svg_path: Path, width: int) -> Image.Image:
    """SVG → PIL Image (지정 너비 기준, 비율 유지, 흰 배경)"""
    png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=width, background_color="white")
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


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


def make_white_version(img: Image.Image) -> Image.Image:
    """투명 배경 + 모든 불투명 픽셀을 흰색으로 (다크 배경 전용)"""
    base = remove_white_bg(img)
    result = base.copy()
    data = result.getdata()
    new_data = []
    for r, g, b, a in data:
        if a < 20:
            new_data.append((0, 0, 0, 0))  # 완전 투명 유지
        else:
            new_data.append((255, 255, 255, a))  # 흰색
    result.putdata(new_data)
    return result


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
    raw = cairosvg.svg2png(url=str(svg_path), output_width=width)
    return Image.open(io.BytesIO(raw)).convert("RGBA")


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
    if svg_path.exists() and logoform is not None:
        try:
            arr = logoform.render(svg_path, 900)
            if arr is not None:
                split = logoform.find_symbol_split(arr, 900)
                if split is not None:
                    cropped = logoform.crop_viewbox(
                        svg_path.read_text(errors="ignore"),
                        split,
                        (arr.shape[1], arr.shape[0]),
                    )
                    if cropped:
                        raw = cairosvg.svg2png(
                            bytestring=cropped.encode(), output_width=size * 4
                        )
                        sym = Image.open(io.BytesIO(raw)).convert("RGBA")
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
        return make_icon(png_to_pil(png_path, 256), size), "whole"
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

    def get_source_img(width):
        if svg_path.exists():
            return svg_to_pil(svg_path, width)
        else:
            return png_to_pil(png_path, width)

    icon_method = {"how": None}

    def _icon():
        img, how = build_icon(svg_path, png_path, 64)
        icon_method["how"] = how
        return img

    targets = {
        "logo-800.png": lambda: get_source_img(800) if svg_path.exists() else None,
        "logo-icon.png": _icon,
        "logo-transparent.png": lambda: remove_white_bg(get_source_img(400)),
        "logo-white.png": lambda: make_white_version(get_source_img(400)),
    }

    transparent_img = None  # 채도 분석용 캐시

    for filename, builder in targets.items():
        out_path = brand_dir / filename
        if out_path.exists():
            results["skipped"].append(filename)
            # 기존 logo-transparent.png로 채도 분석
            if filename == "logo-transparent.png" and out_path.exists():
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", help="특정 브랜드 ID만")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="기존 파일도 덮어쓰기")
    parser.add_argument("--force-icon", action="store_true",
                        help="logo-icon.png만 재생성 (나머지 변형은 보존)")
    parser.add_argument("--report", help="심볼/통짜 판정 결과를 JSON으로 저장할 경로")
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
    brand_map = {b["id"]: b for b in all_brands_data["brands"]}
    updated = 0
    total_created = 0
    icon_stats = {"symbol": [], "whole": []}

    for brand in brands:
        r = process_brand(brand, dry_run=args.dry_run)
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
                updated += 1
                status.append(f"🎨 dark={r['dark_variant']}")

        print(f"[{r['name']}] {' | '.join(status) if status else '변경 없음'}")

    if updated and not args.dry_run:
        all_brands_data["total"] = len(all_brands_data["brands"])
        BRANDS_JSON.write_text(json.dumps(all_brands_data, ensure_ascii=False, indent=2))
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
