#!/usr/bin/env python3
"""
import-project-logos.py — 프로젝트에서 사용 중인 로고 파일을 세모로고 DB에 수집
- PNG만 있어도 추가 (SVG 추후 수집용)
- 기존에 있으면 패스, 없으면 추가
- Usage: python3 scripts/import-project-logos.py [--dry-run]
"""

import json
import shutil
import argparse
from pathlib import Path
from datetime import date

CLIENTS_DIR = Path(__file__).parent.parent / "_clients"
BRANDS_JSON = CLIENTS_DIR / "brands.json"
TODAY = date.today().isoformat()

# 수집 대상: (파일 경로, brand_id, name_ko, name_en, category)
COLLECT_LIST = [
    # premiumpage 자동차 로고
    ("/Volumes/Untitled/dev/nextjs-apps/premiumpage/assets/logo_jaguar.png",
     "jaguar", "재규어", "Jaguar", "자동차"),
    ("/Volumes/Untitled/dev/nextjs-apps/premiumpage/assets/logo_benz.png",
     "mercedes-benz", "메르세데스-벤츠", "Mercedes-Benz", "자동차"),
    ("/Volumes/Untitled/dev/nextjs-apps/premiumpage/assets/logo_vw.png",
     "vw", "폭스바겐 VW", "Volkswagen VW", "자동차"),
    ("/Volumes/Untitled/dev/nextjs-apps/premiumpage/assets/logo_gm.png",
     "general-motors-gm", "제너럴 모터스 GM", "General Motors GM", "자동차"),
    ("/Volumes/Untitled/dev/nextjs-apps/premiumpage/assets/logo_nissan.png",
     "nissan-alt", "닛산", "Nissan", "자동차"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(BRANDS_JSON) as f:
        brands_data = json.load(f)
    existing = brands_data["brands"]
    existing_ids = {b["id"] for b in existing}
    existing_names = {b.get("name_en", "").lower() for b in existing}

    new_brands = []
    for src_path, brand_id, name_ko, name_en, category in COLLECT_LIST:
        src = Path(src_path)
        if not src.exists():
            print(f"  [스킵] 파일 없음: {src_path}")
            continue
        if brand_id in existing_ids:
            print(f"  [이미있음] {brand_id}")
            continue
        if name_en.lower() in existing_names:
            print(f"  [이름중복] {name_en}")
            continue

        if args.dry_run:
            print(f"  [추가예정] {brand_id} / {name_ko} ({src.suffix})")
            new_brands.append(brand_id)
            continue

        brand_dir = CLIENTS_DIR / brand_id
        brand_dir.mkdir(parents=True, exist_ok=True)

        ext = src.suffix.lower()
        if ext == ".svg":
            shutil.copy2(src, brand_dir / "logo.svg")
            logo_svg, logo_png = True, False
        else:
            shutil.copy2(src, brand_dir / "logo.png")
            logo_svg, logo_png = False, True

        entry = {
            "id": brand_id,
            "name_ko": name_ko,
            "name_en": name_en,
            "category": category,
            "logo_svg": logo_svg,
            "logo_png": logo_png,
            "added_at": TODAY,
            "sources": [{"provider": "project-scan", "file": src.name, "label": "프로젝트 에셋"}],
        }
        new_brands.append(entry)
        print(f"  ✅ {brand_id} / {name_ko}")

    print(f"\n기존: {len(existing)}개 | 신규: {len(new_brands)}개")

    if args.dry_run or not new_brands:
        return

    brands_data["brands"] = existing + new_brands
    with open(BRANDS_JSON, "w") as f:
        json.dump(brands_data, f, ensure_ascii=False, indent=2)
    print(f"✅ 완료: +{len(new_brands)}개 → 총 {len(brands_data['brands'])}개")


if __name__ == "__main__":
    main()
