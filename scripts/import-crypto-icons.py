#!/usr/bin/env python3
"""
import-crypto-icons.py — cryptocurrency-icons npm 패키지에서 암호화폐 로고 수집

npm pack cryptocurrency-icons → /tmp/crypto-pkg/package/
  manifest.json: [{symbol, name, color}, ...]
  svg/color/{symbol.lower()}.svg

Usage: python3 scripts/import-crypto-icons.py [--dry-run] [--limit N]
"""

import json
import re
import shutil
import argparse
from pathlib import Path
from datetime import date

try:
    import cairosvg
    HAS_CAIRO = True
except ImportError:
    HAS_CAIRO = False

CLIENTS_DIR = Path(__file__).parent.parent / "_clients"
BRANDS_JSON = CLIENTS_DIR / "brands.json"
PKG_DIR = Path("/tmp/crypto-pkg/package")
SVG_DIR = PKG_DIR / "svg" / "color"
MANIFEST = PKG_DIR / "manifest.json"
TODAY = date.today().isoformat()


def to_id(symbol: str, name: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return slug[:60]


def generate_png(svg_path: Path, out_path: Path, size: int):
    if not HAS_CAIRO:
        return False
    try:
        cairosvg.svg2png(url=str(svg_path), write_to=str(out_path),
                         output_width=size, output_height=size)
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    with open(BRANDS_JSON) as f:
        brands_data = json.load(f)
    existing = brands_data["brands"]
    existing_ids = {b["id"] for b in existing}
    existing_names_lower = {b.get("name_en", "").lower().strip() for b in existing}
    existing_names_lower |= {b.get("name_ko", "").lower().strip() for b in existing}

    with open(MANIFEST) as f:
        manifest = json.load(f)

    new_icons = []
    for coin in manifest:
        symbol = coin["symbol"]
        name = coin["name"]
        brand_id = to_id(symbol, name)
        name_lower = name.lower().strip()

        if brand_id in existing_ids or name_lower in existing_names_lower:
            continue

        svg_file = SVG_DIR / f"{symbol.lower()}.svg"
        if not svg_file.exists():
            alt = SVG_DIR / f"{re.sub(r'[^a-z0-9]','',symbol.lower())}.svg"
            if alt.exists():
                svg_file = alt
            else:
                continue

        coin["_id"] = brand_id
        coin["_svg"] = svg_file
        new_icons.append(coin)

    if args.limit:
        new_icons = new_icons[:args.limit]

    print(f"기존: {len(existing)}개 | 신규 암호화폐: {len(new_icons)}개 | dry-run={args.dry_run}")

    if args.dry_run:
        print("\n[DRY RUN] 상위 30개:")
        for c in new_icons[:30]:
            print(f"  {c['_id']:<35} {c['name']:<30} {c['symbol']}")
        return

    ok, skip_png, new_brands = [], [], []

    for n, coin in enumerate(new_icons, 1):
        brand_id = coin["_id"]
        name = coin["name"]
        symbol = coin["symbol"]
        brand_dir = CLIENTS_DIR / brand_id
        brand_dir.mkdir(parents=True, exist_ok=True)

        svg_dst = brand_dir / "logo.svg"
        shutil.copy2(coin["_svg"], svg_dst)

        png_ok = generate_png(svg_dst, brand_dir / "logo.png", 512)
        if png_ok:
            generate_png(svg_dst, brand_dir / "logo-800.png", 800)
            ok.append(brand_id)
        else:
            skip_png.append(brand_id)

        entry = {
            "id": brand_id,
            "name_ko": name,
            "name_en": name,
            "category": "금융·결제",
            "tags": ["cryptocurrency", symbol.upper()],
            "logo_svg": True,
            "logo_png": png_ok,
            "added_at": TODAY,
        }
        new_brands.append(entry)

        if n % 100 == 0 or n == len(new_icons):
            print(f"  [{n}/{len(new_icons)}] ok={len(ok)} skip_png={len(skip_png)}")

    brands_data["brands"] = existing + new_brands
    with open(BRANDS_JSON, "w") as f:
        json.dump(brands_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 암호화폐 완료: +{len(new_brands)}개 | SVG+PNG={len(ok)} | SVGonly={len(skip_png)}")
    print(f"   brands.json 총 {len(brands_data['brands'])}개")


if __name__ == "__main__":
    main()
