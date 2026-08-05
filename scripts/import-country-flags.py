#!/usr/bin/env python3
"""
import-country-flags.py — flag-icons npm 패키지에서 국가 깃발 수집
- 271개 국가/지역 SVG 깃발
- 카테고리: 국가·지역
- Usage: python3 scripts/import-country-flags.py [--dry-run]
"""

import json
import shutil
import argparse
from pathlib import Path
from datetime import date

try:
    import cairosvg
    HAS_CAIRO = True
except ImportError:
    HAS_CAIRO = False
    print("[경고] cairosvg 없음 — SVG만 저장")

CLIENTS_DIR = Path(__file__).parent.parent / "_clients"
BRANDS_JSON = CLIENTS_DIR / "brands.json"
FLAG_PKG = Path("/tmp/flag-pkg/pkg")
COUNTRY_JSON = FLAG_PKG / "country.json"
FLAGS_DIR = FLAG_PKG / "flags" / "4x3"
TODAY = date.today().isoformat()

# 국가명 한글화 (주요 국가)
KO_NAMES = {
    "Afghanistan": "아프가니스탄", "Albania": "알바니아", "Algeria": "알제리",
    "Andorra": "안도라", "Angola": "앙골라", "Argentina": "아르헨티나",
    "Armenia": "아르메니아", "Australia": "호주", "Austria": "오스트리아",
    "Azerbaijan": "아제르바이잔", "Bahrain": "바레인", "Bangladesh": "방글라데시",
    "Belarus": "벨라루스", "Belgium": "벨기에", "Bolivia": "볼리비아",
    "Bosnia and Herzegovina": "보스니아 헤르체고비나", "Brazil": "브라질",
    "Bulgaria": "불가리아", "Cambodia": "캄보디아", "Canada": "캐나다",
    "Chile": "칠레", "China": "중국", "Colombia": "콜롬비아",
    "Croatia": "크로아티아", "Cuba": "쿠바", "Cyprus": "키프로스",
    "Czech Republic": "체코", "Czechia": "체코", "Denmark": "덴마크",
    "Ecuador": "에콰도르", "Egypt": "이집트", "Estonia": "에스토니아",
    "Ethiopia": "에티오피아", "Finland": "핀란드", "France": "프랑스",
    "Georgia": "조지아", "Germany": "독일", "Ghana": "가나",
    "Greece": "그리스", "Guatemala": "과테말라", "Honduras": "온두라스",
    "Hungary": "헝가리", "Iceland": "아이슬란드", "India": "인도",
    "Indonesia": "인도네시아", "Iran": "이란", "Iraq": "이라크",
    "Ireland": "아일랜드", "Israel": "이스라엘", "Italy": "이탈리아",
    "Jamaica": "자메이카", "Japan": "일본", "Jordan": "요르단",
    "Kazakhstan": "카자흐스탄", "Kenya": "케냐", "Kosovo": "코소보",
    "Kuwait": "쿠웨이트", "Kyrgyzstan": "키르기스스탄", "Laos": "라오스",
    "Latvia": "라트비아", "Lebanon": "레바논", "Libya": "리비아",
    "Liechtenstein": "리히텐슈타인", "Lithuania": "리투아니아",
    "Luxembourg": "룩셈부르크", "Malaysia": "말레이시아", "Malta": "몰타",
    "Mexico": "멕시코", "Moldova": "몰도바", "Monaco": "모나코",
    "Mongolia": "몽골", "Montenegro": "몬테네그로", "Morocco": "모로코",
    "Myanmar": "미얀마", "Nepal": "네팔", "Netherlands": "네덜란드",
    "New Zealand": "뉴질랜드", "Nigeria": "나이지리아",
    "North Korea": "북한", "North Macedonia": "북마케도니아",
    "Norway": "노르웨이", "Oman": "오만", "Pakistan": "파키스탄",
    "Palestine": "팔레스타인", "Panama": "파나마", "Paraguay": "파라과이",
    "Peru": "페루", "Philippines": "필리핀", "Poland": "폴란드",
    "Portugal": "포르투갈", "Qatar": "카타르", "Romania": "루마니아",
    "Russia": "러시아", "Saudi Arabia": "사우디아라비아", "Serbia": "세르비아",
    "Singapore": "싱가포르", "Slovakia": "슬로바키아", "Slovenia": "슬로베니아",
    "Somalia": "소말리아", "South Africa": "남아프리카공화국",
    "South Korea": "대한민국", "Spain": "스페인", "Sri Lanka": "스리랑카",
    "Sudan": "수단", "Sweden": "스웨덴", "Switzerland": "스위스",
    "Syria": "시리아", "Taiwan": "대만", "Tajikistan": "타지키스탄",
    "Thailand": "태국", "Tunisia": "튀니지", "Turkey": "튀르키예",
    "Turkmenistan": "투르크메니스탄", "Uganda": "우간다", "Ukraine": "우크라이나",
    "United Arab Emirates": "아랍에미리트", "United Kingdom": "영국",
    "United States": "미국", "Uruguay": "우루과이", "Uzbekistan": "우즈베키스탄",
    "Venezuela": "베네수엘라", "Vietnam": "베트남", "Yemen": "예멘",
    "Zimbabwe": "짐바브웨", "Kosovo": "코소보",
}


def generate_png(svg_path: Path, out_path: Path, size: int = 512):
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

    with open(COUNTRY_JSON) as f:
        countries = json.load(f)

    new_brands = []
    skip = 0

    for country in countries:
        code = country["code"].lower()
        name_en = country["name"]
        brand_id = f"flag-{code}"

        if brand_id in existing_ids:
            skip += 1
            continue

        svg_src = FLAGS_DIR / f"{code}.svg"
        if not svg_src.exists():
            skip += 1
            continue

        name_ko = KO_NAMES.get(name_en, name_en)

        if args.dry_run:
            print(f"  {brand_id:<20} {name_ko:<20} {name_en}")
            new_brands.append(brand_id)
            continue

        brand_dir = CLIENTS_DIR / brand_id
        brand_dir.mkdir(parents=True, exist_ok=True)

        svg_dst = brand_dir / "logo.svg"
        shutil.copy2(svg_src, svg_dst)

        png_ok = generate_png(svg_dst, brand_dir / "logo.png", 512)

        entry = {
            "id": brand_id,
            "name_ko": name_ko,
            "name_en": name_en,
            "category": "국가·지역",
            "logo_svg": True,
            "logo_png": png_ok,
            "added_at": TODAY,
            "tags": ["국가", "깃발", country.get("continent", "")],
        }
        new_brands.append(entry)

    print(f"기존: {len(existing)}개 | 신규: {len(new_brands)}개 | 스킵: {skip}개")

    if args.dry_run or not new_brands:
        return

    brands_data["brands"] = existing + new_brands
    with open(BRANDS_JSON, "w") as f:
        json.dump(brands_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 완료: +{len(new_brands)}개 → 총 {len(brands_data['brands'])}개")


if __name__ == "__main__":
    main()
