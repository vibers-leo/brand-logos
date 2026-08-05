#!/usr/bin/env python3
"""
import-worldvectorlogo.py — WorldVectorLogo에서 카테고리별 브랜드 SVG 수집

WorldVectorLogo는 sitemap/category 페이지로 브랜드 목록 탐색 가능.
CDN: https://cdn.worldvectorlogo.com/logos/{slug}/{slug}.svg

Usage: python3 scripts/import-worldvectorlogo.py [--dry-run] [--limit N] [--category SLUG]
"""

import json
import re
import time
import ssl
import urllib.request
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
TODAY = date.today().isoformat()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

# 카테고리 페이지 → 우리 카테고리 매핑
WVL_CATEGORIES = [
    ("sports",       "스포츠",      "https://worldvectorlogo.com/sports"),
    ("food",         "식품·음료",   "https://worldvectorlogo.com/food-and-drink"),
    ("fashion",      "뷰티·패션",   "https://worldvectorlogo.com/fashion"),
    ("automotive",   "자동차",      "https://worldvectorlogo.com/automotive"),
    ("media",        "미디어·엔터", "https://worldvectorlogo.com/media"),
    ("finance",      "금융·결제",   "https://worldvectorlogo.com/financial"),
    ("travel",       "숙박·여행",   "https://worldvectorlogo.com/travel"),
    ("healthcare",   "의료·바이오", "https://worldvectorlogo.com/healthcare"),
    ("gaming",       "게임",        "https://worldvectorlogo.com/gaming"),
    ("retail",       "유통·쇼핑",   "https://worldvectorlogo.com/retail"),
    ("education",    "IT·테크",     "https://worldvectorlogo.com/education"),
    ("technology",   "IT·테크",     "https://worldvectorlogo.com/technology"),
    ("telecom",      "통신",        "https://worldvectorlogo.com/telecommunications"),
    ("pets",         "반려동물",    "https://worldvectorlogo.com/pets"),
    ("lifestyle",    "라이프스타일","https://worldvectorlogo.com/lifestyle"),
]

def fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return ""

def fetch_bytes(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
            ct = r.headers.get_content_type() or ""
            data = r.read()
            if "svg" in ct or data[:5] in (b"<?xml", b"<svg "):
                return data
    except Exception:
        pass
    return b""

def extract_slugs_from_page(html: str) -> list:
    # href="/logos/{slug}" 패턴
    return re.findall(r'href="/logos/([a-z0-9-]+)"', html)

def to_title(slug: str) -> str:
    return " ".join(w.capitalize() for w in slug.replace("-", " ").split())

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
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--category", default="", help="특정 카테고리만 (sports/food/...)")
    args = parser.parse_args()

    with open(BRANDS_JSON) as f:
        brands_data = json.load(f)
    existing = brands_data["brands"]
    existing_ids = {b["id"] for b in existing}

    categories = [c for c in WVL_CATEGORIES if not args.category or c[0] == args.category]

    all_new = []
    print(f"카테고리 {len(categories)}개 탐색...")

    for cat_key, cat_label, cat_url in categories:
        print(f"\n[{cat_key}] {cat_url}")

        # 여러 페이지 탐색
        slugs = set()
        for page in range(1, 6):  # 최대 5페이지
            url = f"{cat_url}?page={page}" if page > 1 else cat_url
            html = fetch(url)
            found = extract_slugs_from_page(html)
            if not found:
                break
            new_on_page = [s for s in found if s not in slugs]
            slugs.update(found)
            print(f"  페이지{page}: {len(found)}개 발견 (누적 {len(slugs)}개)")
            if len(found) < 10:
                break
            time.sleep(0.5)

        for slug in slugs:
            if slug in existing_ids:
                continue
            if args.limit and len(all_new) >= args.limit:
                break
            all_new.append({"slug": slug, "category": cat_label})

        if args.limit and len(all_new) >= args.limit:
            break

    print(f"\n신규 대상: {len(all_new)}개")

    if args.dry_run:
        print("[DRY RUN] 상위 30개:")
        for item in all_new[:30]:
            print(f"  {item['slug']:<40} → {item['category']}")
        return

    ok, fail = [], []
    new_brands = []

    for n, item in enumerate(all_new, 1):
        slug = item["slug"]
        category = item["category"]
        brand_dir = CLIENTS_DIR / slug
        brand_dir.mkdir(parents=True, exist_ok=True)

        # SVG 다운로드 시도 (CDN 직접)
        svg_url = f"https://cdn.worldvectorlogo.com/logos/{slug}/{slug}.svg"
        svg_data = fetch_bytes(svg_url)

        if not svg_data or len(svg_data) < 100:
            fail.append(slug)
            if n % 50 == 0:
                print(f"  [{n}/{len(all_new)}] ok={len(ok)} fail={len(fail)}")
            time.sleep(0.3)
            continue

        svg_path = brand_dir / "logo.svg"
        svg_path.write_bytes(svg_data)

        png_ok = generate_png(svg_path, brand_dir / "logo.png", 512)
        if png_ok:
            generate_png(svg_path, brand_dir / "logo-800.png", 800)

        title = to_title(slug)
        entry = {
            "id": slug,
            "name_ko": title,
            "name_en": title,
            "category": category,
            "logo_svg": True,
            "logo_png": png_ok,
            "added_at": TODAY,
        }
        new_brands.append(entry)
        ok.append(slug)

        if n % 50 == 0 or n == len(all_new):
            print(f"  [{n}/{len(all_new)}] ok={len(ok)} fail={len(fail)}")
        time.sleep(0.3)

    brands_data["brands"] = existing + new_brands
    with open(BRANDS_JSON, "w") as f:
        json.dump(brands_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ WVL 완료: +{len(ok)}개 | 실패: {len(fail)}개")
    print(f"   brands.json 총 {len(brands_data['brands'])}개")

if __name__ == "__main__":
    main()
