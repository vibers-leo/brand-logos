#!/usr/bin/env python3
"""
import-gilbarbara.py — gilbarbara/logos GitHub 레포에서 브랜드 SVG 수집
https://github.com/gilbarbara/logos

Usage: python3 scripts/import-gilbarbara.py [--dry-run]
"""

import json, ssl, re, time, shutil, argparse, urllib.request
from pathlib import Path
from datetime import date

CLIENTS_DIR = Path(__file__).parent.parent / "_clients"
BRANDS_JSON  = CLIENTS_DIR / "brands.json"
TODAY = date.today().isoformat()
CTX   = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
RAW_BASE = "https://raw.githubusercontent.com/gilbarbara/logos/main/logos"
API_URL  = "https://api.github.com/repos/gilbarbara/logos/git/trees/main?recursive=1"

# 카테고리 분류 키워드 (파일명 기반)
CAT_MAP = [
    ("암호화폐·블록체인", ["bitcoin","ethereum","solana","polygon","chainlink","uniswap","binance","metamask","opensea","coinbase","avalanche","tron","dogecoin","litecoin"]),
    ("AI·머신러닝",       ["openai","hugging","anthropic","langchain","ollama","mistral","replicate","cohere","stability","midjourney","runpod","together-ai"]),
    ("개발도구",          ["github","gitlab","bitbucket","vscode","vim","neovim","jetbrains","docker","kubernetes","terraform","ansible","vagrant","jenkins","circleci","travis","bash","zsh","fish","powershell","gradle","maven","webpack","vite","rollup","babel","eslint","prettier","jest","vitest","playwright","cypress","storybook","nx","turborepo","bun","deno","node","npm","yarn","pnpm"]),
    ("IT·테크",           ["google","microsoft","apple","meta","amazon","netflix","spotify","slack","notion","figma","atlassian","jira","confluence","airflow","kafka","redis","postgresql","mysql","mongodb","elasticsearch","grafana","datadog","sentry","vercel","netlify","cloudflare","aws","azure","gcp","heroku","supabase","firebase","auth0","okta","stripe","twilio","sendgrid","shopify"]),
    ("게임",              ["unity","unreal","steam","epic","riot","blizzard","ea","nintendo","playstation","xbox","discord","twitch"]),
    ("미디어·엔터",       ["youtube","instagram","twitter","tiktok","snapchat","pinterest","reddit","linkedin","facebook","whatsapp","telegram","medium","substack","wordpress","ghost","wix","squarespace"]),
    ("유통·쇼핑",         ["amazon","ebay","etsy","alibaba","jd","shopify","woocommerce","magento","bigcommerce"]),
    ("금융·결제",         ["visa","mastercard","paypal","stripe","square","klarna","adyen","plaid","brex","revolut","wise"]),
    ("식품·음료",         ["starbucks","mcdonalds","coca","pepsi","nestle","unilever","heinz","kellogg","danone"]),
    ("뷰티·패션",         ["nike","adidas","gucci","prada","zara","hm","uniqlo","levi","gap","lululemon"]),
]

def guess_category(slug: str) -> str:
    s = slug.lower()
    for cat, keywords in CAT_MAP:
        if any(k in s for k in keywords):
            return cat
    return "IT·테크"

def slug_to_names(slug: str):
    clean = re.sub(r'-(icon|wordmark|logo|badge|horizontal|vertical|stacked|original|plain|line|color|dark|light|alt|2|3|4)$', '', slug)
    name_en = re.sub(r'[-_]', ' ', clean).title()
    return name_en, name_en

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, context=CTX, timeout=20).read())

def fetch_svg(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, context=CTX, timeout=10).read()
        if b"<svg" in data:
            return data
    except Exception:
        pass
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(BRANDS_JSON) as f:
        brands_data = json.load(f)
    brands = brands_data["brands"]
    existing_ids = {b["id"] for b in brands}

    # 파일 트리 전체 가져오기
    print("GitHub tree 가져오는 중...")
    tree = fetch_json(API_URL)
    svg_files = [
        item["path"].replace("logos/", "")
        for item in tree["tree"]
        if item["path"].startswith("logos/") and item["path"].endswith(".svg")
    ]
    print(f"총 {len(svg_files)}개 SVG")

    # 아이콘 변형(icon, wordmark 등)은 원본 있으면 스킵 — 원본 없을 때만 포함
    base_slugs = set()
    for fn in svg_files:
        slug = fn.replace(".svg", "")
        base = re.sub(r'-(icon|wordmark|logo|badge|horizontal|vertical|stacked|original|plain|line|color|dark|light|alt)$', '', slug)
        base_slugs.add(base)

    new_brands = []
    skipped = 0

    for fn in svg_files:
        slug = fn.replace(".svg", "")

        # 원본 슬러그가 이미 별도로 있으면 변형 버전 스킵
        base = re.sub(r'-(icon|wordmark|logo|badge|horizontal|vertical|stacked|original|plain|line|color|dark|light|alt)$', '', slug)
        if base != slug and base in base_slugs and base not in existing_ids:
            skipped += 1
            continue

        brand_id = slug
        if brand_id in existing_ids:
            skipped += 1
            continue

        name_en, name_ko = slug_to_names(slug)
        category = guess_category(slug)

        if args.dry_run:
            print(f"  [추가예정] {brand_id:<40} {category}")
            new_brands.append(brand_id)
            continue

        svg_url = f"{RAW_BASE}/{fn}"
        svg_data = fetch_svg(svg_url)
        if not svg_data:
            print(f"  [실패] {fn}")
            continue

        brand_dir = CLIENTS_DIR / brand_id
        brand_dir.mkdir(parents=True, exist_ok=True)
        (brand_dir / "logo.svg").write_bytes(svg_data)

        entry = {
            "id": brand_id,
            "name_ko": name_ko,
            "name_en": name_en,
            "category": category,
            "logo_svg": True,
            "logo_png": False,
            "added_at": TODAY,
            "sources": [{"provider": "gilbarbara-logos", "file": fn, "label": "gilbarbara/logos"}],
        }
        new_brands.append(entry)
        existing_ids.add(brand_id)

        if len(new_brands) % 50 == 0:
            print(f"  [{len(new_brands)}개 추가됨...]")
        time.sleep(0.03)

    print(f"\n스킵: {skipped}개 | 신규: {len(new_brands)}개")

    if args.dry_run or not new_brands:
        return

    brands_data["brands"] = brands + new_brands
    with open(BRANDS_JSON, "w") as f:
        json.dump(brands_data, f, ensure_ascii=False, indent=2)
    print(f"✅ 완료: 총 {len(brands_data['brands'])}개")

if __name__ == "__main__":
    main()
