#!/usr/bin/env python3
"""
import-payment-icons.py — payment-icons npm 패키지에서 결제수단 로고 수집

npm pack payment-icons → /tmp/pay-pkg/package/
  svg/flat/{name}.svg (가장 고품질)

Usage: python3 scripts/import-payment-icons.py [--dry-run]
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
SVG_DIR = Path("/tmp/pay-pkg/package/svg/flat")
TODAY = date.today().isoformat()

# slug → 브랜드명 매핑
NAME_MAP = {
    "alipay": "Alipay",
    "amex": "American Express",
    "default": None,       # 스킵
    "diners": "Diners Club",
    "discover": "Discover",
    "elo": "Elo",
    "hipercard": "Hipercard",
    "jcb": "JCB",
    "maestro": "Maestro",
    "maestro-old": None,   # 구버전 스킵
    "mastercard": "Mastercard",
    "mastercard-old": None,
    "paypal": "PayPal",
    "security-code": None,
    "unionpay": "UnionPay",
    "verve": "Verve",
    "visa": "Visa",
}


def to_id(slug: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', slug.lower()).strip('-')


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
    args = parser.parse_args()

    with open(BRANDS_JSON) as f:
        brands_data = json.load(f)
    existing = brands_data["brands"]
    existing_ids = {b["id"] for b in existing}
    existing_names_lower = {b.get("name_en", "").lower().strip() for b in existing}

    new_icons = []
    for svg_file in sorted(SVG_DIR.glob("*.svg")):
        slug = svg_file.stem
        name = NAME_MAP.get(slug)
        if name is None:
            continue

        brand_id = to_id(slug)
        if brand_id in existing_ids or name.lower() in existing_names_lower:
            continue

        new_icons.append({"id": brand_id, "name": name, "svg": svg_file})

    print(f"기존: {len(existing)}개 | 신규 결제수단: {len(new_icons)}개 | dry-run={args.dry_run}")

    if args.dry_run:
        for item in new_icons:
            print(f"  {item['id']:<20} {item['name']}")
        return

    ok, new_brands = [], []

    for item in new_icons:
        brand_dir = CLIENTS_DIR / item["id"]
        brand_dir.mkdir(parents=True, exist_ok=True)

        svg_dst = brand_dir / "logo.svg"
        shutil.copy2(item["svg"], svg_dst)

        png_ok = generate_png(svg_dst, brand_dir / "logo.png", 512)
        if png_ok:
            generate_png(svg_dst, brand_dir / "logo-800.png", 800)
            ok.append(item["id"])

        entry = {
            "id": item["id"],
            "name_ko": item["name"],
            "name_en": item["name"],
            "category": "금융·결제",
            "logo_svg": True,
            "logo_png": png_ok,
            "added_at": TODAY,
        }
        new_brands.append(entry)
        print(f"  ✓ {item['name']}")

    brands_data["brands"] = existing + new_brands
    with open(BRANDS_JSON, "w") as f:
        json.dump(brands_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 결제수단 완료: +{len(new_brands)}개 | SVG+PNG={len(ok)}")
    print(f"   brands.json 총 {len(brands_data['brands'])}개")


if __name__ == "__main__":
    main()
