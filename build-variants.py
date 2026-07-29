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

import argparse, json, sys
from pathlib import Path
import cairosvg
from PIL import Image
import io

BASE = Path(__file__).parent / "_clients"
BRANDS_JSON = BASE / "brands.json"


def svg_to_pil(svg_path: Path, width: int) -> Image.Image:
    """SVG → PIL Image (지정 너비 기준, 비율 유지)"""
    png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=width)
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


def make_icon(img: Image.Image, size: int = 64) -> Image.Image:
    """정사각형 아이콘 크기로 리사이즈 (여백 추가해 비율 유지)"""
    base = remove_white_bg(img)
    base.thumbnail((size, size), Image.LANCZOS)
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - base.width) // 2
    y = (size - base.height) // 2
    icon.paste(base, (x, y), base)
    return icon


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

    targets = {
        "logo-800.png": lambda: get_source_img(800) if svg_path.exists() else None,
        "logo-icon.png": lambda: make_icon(get_source_img(256), 64),
        "logo-transparent.png": lambda: remove_white_bg(get_source_img(400)),
        "logo-white.png": lambda: make_white_version(get_source_img(400)),
    }

    for filename, builder in targets.items():
        out_path = brand_dir / filename
        if out_path.exists():
            results["skipped"].append(filename)
            continue

        if dry_run:
            # logo-800은 SVG 없으면 건너뜀
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
        except Exception as e:
            results["errors"].append(f"{filename}: {e}")

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", help="특정 브랜드 ID만")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="기존 파일도 덮어쓰기")
    args = parser.parse_args()

    brands = json.loads(BRANDS_JSON.read_text())["brands"]
    if args.brand:
        brands = [b for b in brands if b["id"] == args.brand]
        if not brands:
            print(f"❌ 브랜드 '{args.brand}' 없음")
            sys.exit(1)

    if args.force:
        # 기존 변형 파일 삭제 후 재생성
        for brand in brands:
            d = BASE / brand["id"]
            for f in ["logo-800.png", "logo-icon.png", "logo-transparent.png", "logo-white.png"]:
                p = d / f
                if p.exists():
                    p.unlink()

    total_created = 0
    for brand in brands:
        r = process_brand(brand, dry_run=args.dry_run)
        status = []
        if r["created"]:
            status.append(f"✅ {', '.join(r['created'])}")
            total_created += len(r["created"])
        if r["skipped"]:
            status.append(f"⏭  {', '.join(r['skipped'])}")
        if r["errors"]:
            status.append(f"❌ {', '.join(r['errors'])}")
        print(f"[{r['name']}] {' | '.join(status) if status else '변경 없음'}")

    print(f"\n완료: {total_created}개 파일 생성")


if __name__ == "__main__":
    main()
