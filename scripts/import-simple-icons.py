#!/usr/bin/env python3
"""
import-simple-icons.py — Simple Icons 3,453개 → 세모로고 브랜드 DB 자동 통합

1. Simple Icons npm 패키지에서 신규 브랜드 추출
2. 카테고리 키워드 매핑
3. SVG 복사 + PNG 800px 생성 (cairosvg)
4. brands.json 업데이트
5. added_at 날짜 태깅

Usage: python3 scripts/import-simple-icons.py [--dry-run] [--limit N]
"""

import json
import re
import sys
import shutil
import argparse
from pathlib import Path
from datetime import date

try:
    import cairosvg
    HAS_CAIRO = True
except ImportError:
    HAS_CAIRO = False
    print("[경고] cairosvg 없음 — SVG만 저장, PNG 생성 스킵")

# ── 경로 설정 ──────────────────────────────────────────────
CLIENTS_DIR = Path(__file__).parent.parent / "_clients"
BRANDS_JSON = CLIENTS_DIR / "brands.json"
SI_ICONS_DIR = Path("/tmp/package/icons")
SI_DATA = Path("/tmp/package/data/simple-icons.json")
TODAY = date.today().isoformat()

# ── 카테고리 키워드 매핑 ────────────────────────────────────
GAME_KW = {
    "steam","playstation","xbox","nintendo","epicgames","ea","activision",
    "blizzard","riot","ubisoft","unity","unreal","godot","itch","gog",
    "twitch","discord","battlenet","origin","bethesda","2k","rockstar",
    "sega","capcom","konami","bandainamco","squareenix","embracer",
    "playstationnetwork","xboxgamepass","nvidiageforce","razer",
    "corsair","steelseries","logitech","alienware","asus","msi",
    "redbull","esea","faceit","challonge","battlefy","toornament",
    "leagueoflegends","minecraft","roblox","fortnite","pubg","valorant",
    "csgo","overwatch","dota","hearthstone","clash","pokemon",
    "genshin","honkai","starcraft","warcraft","diablo","fifa","pes",
    "nba2k","madden","callofduty","apexlegends","rainbowsix",
}
FINANCE_KW = {
    "paypal","stripe","visa","mastercard","americanexpress","amex",
    "discover","bitcoin","ethereum","binance","coinbase","kraken",
    "opensea","metamask","litecoin","dogecoin","ripple","cardano",
    "polkadot","chainlink","uniswap","aave","compound","makerdao",
    "tether","usdc","bnb","solana","avalanche","polygon","fantom",
    "terra","near","algorand","stellar","tron","eos","monero",
    "zcash","dash","iota","nano","vechain","hedera","flow","elrond",
    "wealthsimple","robinhood","sofi","chime","venmo","cashapp",
    "zelle","klarna","affirm","afterpay","plaid","wise","revolut",
    "n26","monzo","starling","transferwise","payoneer","skrill",
    "neteller","paysafecard","qiwi","yoomoney","paytm","razorpay",
    "phonepe","googlepay","applepay","samsungpay","alipay","wechatpay",
}
MEDIA_KW = {
    "netflix","spotify","youtube","hulu","disneyplus","appletv",
    "hbomax","primevideo","peacock","paramount","crunchyroll","funimation",
    "tidal","soundcloud","deezer","pandora","iheartradio","audible",
    "buzzfeed","vice","vox","wired","theverge","techcrunch","mashable",
    "engadget","arstechnica","cnet","bbc","cnn","nbc","abc","fox",
    "msnbc","bloomberg","reuters","ap","apnews","guardian","nytimes",
    "washingtonpost","wsj","forbes","businessinsider","huffpost",
    "dailymail","telegraph","independent","economist","time","newsweek",
    "medium","substack","beehiiv","ghost","wordpress","tumblr",
    "blogger","weebly","wix","squarespace","anchor","buzzsprout",
    "podbean","libsyn","transistor","simplecast","fireside","art19",
    "vimeo","dailymotion","rumble","odysee","bitchute","peertube",
    "storyblok","contentful","sanity","prismic","strapi","directus",
    "canva","figma","behance","dribbble","pinterest",
}
SOCIAL_KW = {
    "facebook","instagram","twitter","x","tiktok","snapchat","linkedin",
    "reddit","quora","discord","telegram","whatsapp","signal","line",
    "kakao","wechat","viber","skype","zoom","teams","slack","matrix",
    "mastodon","bluesky","threads","clubhouse","bereal","tumblr",
    "vk","weibo","baidu","douyin","kuaishou","xiaohongshu","bilibili",
}
FASHION_KW = {
    "gucci","louisvuitton","lv","chanel","prada","hermes","dior",
    "versace","burberry","armani","zara","hm","uniqlo","gap","levi",
    "nike","adidas","puma","reebok","underarmour","newbalance",
    "vans","converse","timberland","dr martens","birkenstock","crocs",
    "pandora","swarovski","tiffany","cartier","rolex","omega","tag",
}
FOOD_KW = {
    "mcdonalds","starbucks","subway","kfc","burgerking","pizzahut",
    "dominoes","tacobell","chipotle","panda","wendys","popeyes",
    "dunkin","timhortons","cocacola","pepsi","redbull","monster",
    "budweiser","heineken","corona","guinness","absolut","jackdaniels",
    "nestle","danone","kellogg","campbells","kraft","heinz","unilever",
    "mondelez","mars","ferrero","lindt","godiva","hershey","milka",
}
AUTO_KW = {
    "tesla","bmw","mercedes","volkswagen","audi","porsche","ferrari",
    "lamborghini","maserati","bugatti","bentley","rollsroyce","astonmartin",
    "jaguar","landrover","volvo","saab","peugeot","renault","citroen",
    "toyota","honda","nissan","mazda","subaru","mitsubishi","lexus",
    "infiniti","acura","suzuki","daihatsu","isuzu","hyundai","kia",
    "genesis","ssangyong","chevrolet","ford","gmc","cadillac","dodge",
    "chrysler","jeep","ram","buick","lincoln","rivian","lucid","fisker",
    "nio","byd","xpeng","li","saic","geely","baic","chery","greatawall",
    "uber","lyft","waymo","zoox","cruise","argo",
}
HEALTH_KW = {
    "pfizer","moderna","astrazeneca","johnsonandjohnson","merck","abbott",
    "novartis","roche","sanofi","bayer","eli","lilly","bristol",
    "amgen","biogen","gilead","regeneron","vertex","alexion","shire",
    "medtronic","stryker","becton","edwards","zimmer","hologic",
    "illumina","bio","qiagen","bruker","waters","mettler","perkin",
    "cvs","walgreens","rite","express","mckesson","amerisource",
    "cardinal","optum","aetna","unitedhealth","anthem","cigna","humana",
}
CLOUD_KW = {
    "amazonaws","awsamplify","microsoftazure","googlecloud","cloudflare",
    "digitalocean","linode","vultr","hetzner","ovhcloud","scaleway",
    "vercel","netlify","heroku","railway","render","flyio","coolify",
    "kubernetes","docker","podman","terraform","ansible","puppet","chef",
    "jenkins","github","gitlab","bitbucket","circleci","travisci",
    "sonarqube","jfrog","nexus","artifactory","datadog","newrelic",
    "dynatrace","splunk","elastic","grafana","prometheus","influxdb",
    "pagerduty","opsgenie","statuspage","pingdom","uptimerobot",
}
EDUCATION_KW = {
    "coursera","udemy","edx","pluralsight","linkedin","skillshare",
    "masterclass","duolingo","babbel","rosetta","codecademy","freecodecamp",
    "khanacademy","treehouse","datacamp","udacity","brilliant","curiositystream",
}


def map_category(title: str, slug: str, source: str) -> str:
    t = (title + " " + slug + " " + source).lower()
    t = re.sub(r'[^a-z0-9 ]', '', t)
    words = set(t.split())

    def hit(kw_set):
        return bool(words & kw_set) or any(k in t for k in kw_set if len(k) > 4)

    if hit(GAME_KW):        return "게임"
    if hit(FINANCE_KW):     return "금융·결제"
    if hit(SOCIAL_KW):      return "미디어·엔터"
    if hit(MEDIA_KW):       return "미디어·엔터"
    if hit(FASHION_KW):     return "뷰티·패션"
    if hit(FOOD_KW):        return "식품·음료"
    if hit(AUTO_KW):        return "자동차"
    if hit(HEALTH_KW):      return "의료·바이오"
    if hit(EDUCATION_KW):   return "IT·테크"
    if hit(CLOUD_KW):       return "IT·테크"
    return "IT·테크"


def to_id(slug: str, title: str) -> str:
    s = slug or re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return s[:60]


def extract_domain(source: str) -> str:
    if not source:
        return ""
    m = re.match(r'https?://([^/]+)', source)
    if not m:
        return ""
    d = m.group(1).lstrip("www.")
    # source가 github이면 도메인 못 씀
    if d in ("github.com", "commons.wikimedia.org", "en.wikipedia.org"):
        return ""
    return d


def generate_png(svg_path: Path, out_path: Path, size: int = 800):
    if not HAS_CAIRO:
        return False
    try:
        cairosvg.svg2png(url=str(svg_path), write_to=str(out_path),
                         output_width=size, output_height=size)
        return True
    except Exception as e:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    # 기존 brands.json 로드
    with open(BRANDS_JSON) as f:
        brands_data = json.load(f)
    existing = brands_data["brands"]

    existing_ids = {b["id"] for b in existing}
    existing_names_lower = {b.get("name_en", "").lower().strip() for b in existing}
    existing_names_lower |= {b.get("name_ko", "").lower().strip() for b in existing}

    # Simple Icons 로드
    with open(SI_DATA) as f:
        si_icons = json.load(f)

    # 신규 필터링
    new_icons = []
    for icon in si_icons:
        title = icon["title"]
        slug = icon.get("slug") or re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        brand_id = to_id(slug, title)
        name_lower = title.lower().strip()

        if brand_id in existing_ids:
            continue
        if name_lower in existing_names_lower:
            continue

        svg_src = SI_ICONS_DIR / f"{slug}.svg"
        if not svg_src.exists():
            # 일부 slug vs 파일명 불일치 → title 기반 시도
            alt = re.sub(r'[^a-z0-9]', '', title.lower())
            alt_path = SI_ICONS_DIR / f"{alt}.svg"
            if alt_path.exists():
                svg_src = alt_path
            else:
                continue  # SVG 없으면 스킵

        icon["_id"] = brand_id
        icon["_svg_src"] = svg_src
        new_icons.append(icon)

    if args.limit:
        new_icons = new_icons[:args.limit]

    print(f"기존: {len(existing)}개 | 신규: {len(new_icons)}개 | dry-run={args.dry_run}")

    if args.dry_run:
        print("\n[DRY RUN] 상위 30개 미리보기:")
        for i in new_icons[:30]:
            cat = map_category(i["title"], i.get("slug",""), i.get("source",""))
            domain = extract_domain(i.get("source",""))
            print(f"  {i['_id']:<35} {i['title']:<30} {cat:<15} {domain}")
        return

    ok, skip_png, fail = [], [], []
    new_brands = []

    for n, icon in enumerate(new_icons, 1):
        brand_id = icon["_id"]
        title = icon["title"]
        slug = icon.get("slug", brand_id)
        source = icon.get("source", "")
        brand_dir = CLIENTS_DIR / brand_id
        brand_dir.mkdir(parents=True, exist_ok=True)

        svg_dst = brand_dir / "logo.svg"
        png_dst = brand_dir / "logo.png"
        png800_dst = brand_dir / "logo-800.png"

        # SVG 복사
        shutil.copy2(icon["_svg_src"], svg_dst)

        # PNG 생성
        png_ok = generate_png(svg_dst, png_dst, 512)
        if png_ok:
            generate_png(svg_dst, png800_dst, 800)
            ok.append(brand_id)
        else:
            skip_png.append(brand_id)

        category = map_category(title, slug, source)
        domain = extract_domain(source)

        entry = {
            "id": brand_id,
            "name_ko": title,
            "name_en": title,
            "category": category,
            "logo_svg": True,
            "logo_png": png_ok,
            "added_at": TODAY,
        }
        if domain:
            entry["domain"] = domain

        new_brands.append(entry)

        if n % 100 == 0 or n == len(new_icons):
            print(f"  [{n}/{len(new_icons)}] 완료 {len(ok)}개, PNG스킵 {len(skip_png)}개")

    # brands.json 업데이트
    brands_data["brands"] = existing + new_brands
    with open(BRANDS_JSON, "w") as f:
        json.dump(brands_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 완료: +{len(new_brands)}개 | SVG+PNG={len(ok)} | SVGonly={len(skip_png)}")
    print(f"   brands.json 총 {len(brands_data['brands'])}개")


if __name__ == "__main__":
    main()
