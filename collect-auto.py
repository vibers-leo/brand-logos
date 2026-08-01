#!/usr/bin/env python3
"""
한국 브랜드 SVG 자동 수집 파이프라인

소스:
  1. Wikimedia Commons — Category:SVG logos of companies of South Korea 등
  2. Simple Icons — 한국 브랜드 필터
  3. Font Awesome Free Brands — 소스 비교용

실행:
  python3 collect-auto.py                  # 전체 실행
  python3 collect-auto.py --source wiki    # Wikimedia만
  python3 collect-auto.py --source simple  # Simple Icons만
  python3 collect-auto.py --source fa      # Font Awesome만 (sources/ 저장)
  python3 collect-auto.py --source sources # 기존 브랜드에 FA/SI 소스 추가
  python3 collect-auto.py --dry-run        # 다운로드 없이 목록만
"""

import argparse, json, os, re, subprocess, sys, time, unicodedata, urllib.parse, urllib.request
from pathlib import Path

BASE      = Path(__file__).parent
LOGO_DIR  = BASE / "_clients"
BRANDS_JSON = LOGO_DIR / "brands.json"
UA = "VibersLogoDB/1.0 (vibers.leo@gmail.com)"

# Wikimedia Commons 수집 대상 카테고리
WIKI_CATEGORIES = [
    "SVG logos of companies of South Korea",
    "SVG logos of organizations of South Korea",
    "Logos of companies of South Korea",
    "Government logos of South Korea",
    "Logos of banks of South Korea",
    "Logos of television channels of South Korea",
    "Logos of universities and colleges in South Korea",
    "Logos of sports teams of South Korea",
    "SVG logos of South Korean entertainment companies",
    "Logos of airlines of South Korea",
    "SVG logos of retail companies of South Korea",
    "Logos of South Korean companies",
    "SVG logos of financial companies of South Korea",
    "Logos of Korean companies",
    # 추가 카테고리
    "Logos of banks in South Korea",
    "Logos of media companies in South Korea",
    "Logos of supermarkets of South Korea",
    "Kakao",
    "CJ Group",
    "GS Group",
    "POSCO",
    # 공공기관 추가
    "Logos of television channels in South Korea",
    "Logos of hospitals in South Korea",
    "Logos of public transport in South Korea",
    "Logos of universities in South Korea",
]

# 이미 등록된 브랜드 ID 로드
def load_existing_ids() -> set[str]:
    if not BRANDS_JSON.exists():
        return set()
    data = json.loads(BRANDS_JSON.read_text())
    return {b["id"] for b in data.get("brands", [])}


def load_brands_json() -> dict:
    if not BRANDS_JSON.exists():
        return {"total": 0, "source": "vibers-logo-db", "brands": []}
    return json.loads(BRANDS_JSON.read_text())


def save_brands_json(data: dict):
    data["total"] = len(data["brands"])
    BRANDS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def slugify(text: str) -> str:
    """한글·특수문자 → 영문 slug"""
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.ASCII).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def wiki_api(params: dict, site="commons.wikimedia.org") -> dict:
    params["format"] = "json"
    url = f"https://{site}/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_file_url(filename: str) -> str | None:
    """Wikimedia 파일명 → 실제 다운로드 URL"""
    data = wiki_api({
        "action": "query",
        "titles": f"File:{filename}",
        "prop": "imageinfo",
        "iiprop": "url|mediatype",
    })
    pages = data["query"]["pages"]
    page = next(iter(pages.values()))
    infos = page.get("imageinfo", [])
    if not infos:
        return None
    info = infos[0]
    if info.get("mediatype") != "DRAWING":  # SVG만
        return None
    return info["url"]


def collect_wikimedia(dry_run=False) -> list[dict]:
    """Wikimedia Commons 카테고리에서 한국 SVG 로고 수집"""
    existing = load_existing_ids()
    collected = []

    for category in WIKI_CATEGORIES:
        print(f"\n📂 {category}")
        cmcontinue = None

        while True:
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": f"Category:{category}",
                "cmtype": "file",
                "cmlimit": "100",
                "cmprop": "title|timestamp",
            }
            if cmcontinue:
                params["cmcontinue"] = cmcontinue

            data = wiki_api(params)
            members = data.get("query", {}).get("categorymembers", [])

            for m in members:
                title = m["title"]  # "File:Samsung_Logo.svg"
                filename = title.replace("File:", "")

                # SVG 파일만
                if not filename.lower().endswith(".svg"):
                    continue

                # slug 생성 (파일명 기반)
                name = re.sub(r"\.svg$", "", filename, flags=re.IGNORECASE)
                name = re.sub(r"[_\s]+logo.*$", "", name, flags=re.IGNORECASE)
                name = re.sub(r"[_\s]+", "-", name).lower()
                brand_id = re.sub(r"[^a-z0-9-]", "", name).strip("-")

                if not brand_id or len(brand_id) < 2:
                    continue
                if brand_id in existing:
                    print(f"  ⏭  {brand_id} (이미 있음)")
                    continue

                print(f"  🔍 {brand_id} ← {filename}")

                if dry_run:
                    collected.append({"id": brand_id, "filename": filename})
                    existing.add(brand_id)
                    continue

                # 실제 다운로드 URL 조회
                try:
                    url = get_file_url(filename)
                    if not url:
                        print(f"     ⚠️  SVG URL 없음")
                        continue
                    time.sleep(0.3)  # API rate limit
                except Exception as e:
                    print(f"     ❌ URL 조회 실패: {e}")
                    continue

                # SVG 다운로드 + 검증
                try:
                    result = download_svg(brand_id, url, filename)
                    if result:
                        collected.append(result)
                        existing.add(brand_id)
                        time.sleep(0.5)
                except Exception as e:
                    print(f"     ❌ 다운로드 실패: {e}")

            # 페이지네이션
            cont = data.get("continue", {})
            cmcontinue = cont.get("cmcontinue")
            if not cmcontinue:
                break
            time.sleep(0.3)

    return collected


def download_svg(brand_id: str, url: str, filename: str) -> dict | None:
    """SVG 다운로드 → 검증 → 저장 → brands.json 항목 반환"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()

    # UTF-16 BOM 처리
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        enc = "utf-16-le" if raw[:2] == b"\xff\xfe" else "utf-16-be"
        content = raw.decode(enc).encode("utf-8")
    else:
        content = raw

    # 품질 검증
    if b"<svg" not in content.lower():
        print(f"     ⚠️  SVG 태그 없음")
        return None
    if b"data:image/" in content:
        print(f"     ⚠️  base64 비트맵 내장 — 스킵")
        return None
    if b"<image" in content and b"data:image" in content:
        print(f"     ⚠️  래스터 이미지 내장 — 스킵")
        return None

    # 저장
    dest_dir = LOGO_DIR / brand_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    svg_path = dest_dir / "logo.svg"
    svg_path.write_bytes(content)

    print(f"     ✅ 저장 ({len(content):,}B)")

    # 브랜드 이름 추출 (파일명 기반)
    name = re.sub(r"\.svg$", "", filename, flags=re.IGNORECASE)
    name = re.sub(r"[_-]", " ", name).strip()
    name = re.sub(r"\s*(logo|Logo|LOGO).*$", "", name).strip()

    return {
        "id": brand_id,
        "name_ko": name,
        "name_en": name,
        "category": "기업",          # 기본값 — 나중에 수동 분류
        "domain": "",
        "logo_svg": True,
        "source": f"wikimedia:{filename}",
        "status": "raw",             # internalize + variants 미완료 표시
    }


def collect_simple_icons(dry_run=False) -> list[dict]:
    """Simple Icons에서 한국 브랜드 필터링"""
    existing = load_existing_ids()

    # simple-icons data.json (HEAD 브랜치)
    si_url = "https://raw.githubusercontent.com/simple-icons/simple-icons/HEAD/data/simple-icons.json"
    print(f"\n📦 Simple Icons 로드 중...")
    req = urllib.request.Request(si_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            si_data = json.loads(r.read())
    except Exception as e:
        print(f"  ❌ 로드 실패: {e}")
        return []

    icons = si_data if isinstance(si_data, list) else si_data.get("icons", [])
    print(f"  총 {len(icons)}개 아이콘")

    # Simple Icons 전용 한국 브랜드 키워드 (명확한 한국 브랜드명만, 오탐 방지)
    KR_KEYWORDS = [
        # 대기업·IT (정확한 이름 매칭)
        "samsung", "hyundai", "kakao", "naver", "kia", "nexon",
        "krafton", "ncsoft", "netmarble", "smilegate", "devsisters",
        "kakaobank", "kakaopay", "kakaotalk",
        "hybe", "lotte", "hanwha", "posco", "doosan",
        "sk telecom", "lg uplus", "kt telecom",
        "korea", "korean",
        # 장문 키워드 (중복 없음)
        "coupang", "toss", "upbit", "dunamu",
        "amorepacific", "laneige", "sulwhasoo",
        "nongshim", "ottogi", "binggrae",
        "shinhan", "woori bank", "hana bank",
        "samsung pay",
    ]

    collected = []
    for icon in icons:
        title = icon.get("title", "").lower()
        # Simple Icons slug: lowercase, alphanumeric only (spaces/special chars removed)
        si_slug = re.sub(r"[^a-z0-9]", "", title)
        # brand_id uses hyphen-slug for readability
        brand_id = icon.get("slug", "") or slugify(icon.get("title", ""))

        # 한국 브랜드 감지
        is_kr = any(kw in title for kw in KR_KEYWORDS)
        if not is_kr:
            continue

        if brand_id in existing:
            print(f"  ⏭  {brand_id} (이미 있음)")
            continue

        hex_color = icon.get("hex", "000000")
        print(f"  🔍 {brand_id} — {icon['title']} (#{hex_color})")

        if dry_run:
            collected.append({"id": brand_id, "title": icon["title"]})
            existing.add(brand_id)
            continue

        # Simple Icons SVG URL (HEAD branch, alphanumeric slug)
        svg_url = f"https://raw.githubusercontent.com/simple-icons/simple-icons/HEAD/icons/{si_slug}.svg"
        try:
            result = download_svg(brand_id, svg_url, f"{si_slug}.svg")
            if result:
                result["source"] = f"simple-icons:{si_slug}"
                result["name_en"] = icon["title"]
                result["brand_color"] = f"#{hex_color}"
                collected.append(result)
                existing.add(brand_id)
                time.sleep(0.3)
        except Exception as e:
            print(f"     ❌ {e}")

    return collected


def generate_base_png(brand_id: str):
    """logo.svg → logo.png (카드 미리보기용 400px)"""
    import cairosvg, io
    from PIL import Image
    svg_path = LOGO_DIR / brand_id / "logo.svg"
    png_path = LOGO_DIR / brand_id / "logo.png"
    if png_path.exists() or not svg_path.exists():
        return
    try:
        png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=400, background_color="white")
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        img.save(png_path)
    except Exception as e:
        print(f"     ⚠️  logo.png 생성 실패: {e}")


def run_pipeline(brand_id: str):
    """logo.png 생성 → internalize-svg → build-variants 실행"""
    print(f"  🔧 파이프라인: {brand_id}")
    try:
        generate_base_png(brand_id)
        subprocess.run(
            [sys.executable, str(BASE / "internalize-svg.py"), "--brand", brand_id],
            cwd=BASE, capture_output=True, timeout=30
        )
        subprocess.run(
            [sys.executable, str(BASE / "build-variants.py"), "--brand", brand_id],
            cwd=BASE, capture_output=True, timeout=60
        )
        print(f"     ✅ 완료")
    except Exception as e:
        print(f"     ⚠️  파이프라인 오류: {e}")


# Font Awesome Free Brands — 소스 비교 대상 (브랜드명: FA slug)
FA_TARGETS = {
    # 소셜/커뮤니티
    "facebook": ("Facebook", "소셜미디어"), "instagram": ("Instagram", "소셜미디어"),
    "youtube": ("YouTube", "미디어"), "tiktok": ("TikTok", "소셜미디어"),
    "x-twitter": ("X (Twitter)", "소셜미디어"), "twitter": ("Twitter", "소셜미디어"),
    "linkedin": ("LinkedIn", "소셜미디어"), "pinterest": ("Pinterest", "소셜미디어"),
    "reddit": ("Reddit", "소셜미디어"), "discord": ("Discord", "커뮤니티"),
    "threads": ("Threads", "소셜미디어"), "bluesky": ("Bluesky", "소셜미디어"),
    "mastodon": ("Mastodon", "소셜미디어"),
    # 테크/클라우드
    "google": ("Google", "전자/IT"), "apple": ("Apple", "전자/IT"),
    "microsoft": ("Microsoft", "전자/IT"), "amazon": ("Amazon", "이커머스"),
    "meta": ("Meta", "전자/IT"), "aws": ("Amazon Web Services", "전자/IT"),
    "cloudflare": ("Cloudflare", "전자/IT"), "docker": ("Docker", "전자/IT"),
    "github": ("GitHub", "전자/IT"), "gitlab": ("GitLab", "전자/IT"),
    "slack": ("Slack", "전자/IT"), "figma": ("Figma", "전자/IT"),
    "dropbox": ("Dropbox", "전자/IT"), "notion": ("Notion", "전자/IT"),
    # 브라우저/OS
    "chrome": ("Google Chrome", "전자/IT"), "firefox": ("Firefox", "전자/IT"),
    "safari": ("Safari", "전자/IT"), "edge": ("Microsoft Edge", "전자/IT"),
    "android": ("Android", "전자/IT"), "windows": ("Windows", "전자/IT"),
    "linux": ("Linux", "전자/IT"),
    # 게임
    "steam": ("Steam", "게임"), "playstation": ("PlayStation", "게임"),
    "xbox": ("Xbox", "게임"), "twitch": ("Twitch", "게임"),
    "battle-net": ("Battle.net", "게임"),
    # 스트리밍/미디어
    "spotify": ("Spotify", "미디어"), "soundcloud": ("SoundCloud", "미디어"),
    "vimeo": ("Vimeo", "미디어"), "bilibili": ("Bilibili", "미디어"),
    # 결제
    "cc-visa": ("Visa", "금융/보험"), "cc-mastercard": ("Mastercard", "금융/보험"),
    "cc-amex": ("American Express", "금융/보험"), "cc-jcb": ("JCB", "금융/보험"),
    "paypal": ("PayPal", "핀테크"), "cc-paypal": ("PayPal", "핀테크"),
    "cc-stripe": ("Stripe", "핀테크"), "stripe": ("Stripe", "핀테크"),
    "cc-apple-pay": ("Apple Pay", "핀테크"), "google-pay": ("Google Pay", "핀테크"),
    "amazon-pay": ("Amazon Pay", "핀테크"),
    # 개발도구
    "node": ("Node.js", "전자/IT"), "react": ("React", "전자/IT"),
    "vuejs": ("Vue.js", "전자/IT"), "angular": ("Angular", "전자/IT"),
    "bootstrap": ("Bootstrap", "전자/IT"),
    # 앱스토어
    "google-play": ("Google Play", "전자/IT"), "app-store-ios": ("App Store", "전자/IT"),
    # 이커머스
    "shopify": ("Shopify", "유통/쇼핑"), "ebay": ("eBay", "이커머스"),
    "etsy": ("Etsy", "이커머스"), "airbnb": ("Airbnb", "숙박/여행"),
    # 기타
    "wordpress": ("WordPress", "전자/IT"), "bitcoin": ("Bitcoin", "핀테크"),
    "behance": ("Behance", "미디어"), "artstation": ("ArtStation", "미디어"),
}

FA_RAW_BASE = "https://raw.githubusercontent.com/FortAwesome/Font-Awesome/6.x/svgs/brands"

# Simple Icons 글로벌 인기 브랜드 (CDN slug → (name_en, name_ko, category))
SI_GLOBAL_TARGETS = {
    # 스포츠
    "nike":         ("Nike", "나이키", "스포츠"),
    "adidas":       ("Adidas", "아디다스", "스포츠"),
    "puma":         ("Puma", "퓨마", "스포츠"),
    "newbalance":   ("New Balance", "뉴발란스", "스포츠"),
    "underarmour":  ("Under Armour", "언더아머", "스포츠"),
    # 식음료
    "mcdonalds":    ("McDonald's", "맥도날드", "식음료"),
    "burgerking":   ("Burger King", "버거킹", "식음료"),
    "kfc":          ("KFC", "KFC", "식음료"),
    "cocacola":     ("Coca-Cola", "코카콜라", "식음료"),
    # 미디어/스트리밍
    "netflix":      ("Netflix", "넷플릭스", "스트리밍"),
    "hbo":          ("HBO", "HBO", "스트리밍"),
    "cnn":          ("CNN", "CNN", "미디어"),
    "nbc":          ("NBC", "NBC", "미디어"),
    "fox":          ("Fox", "Fox", "미디어"),
    # 자동차
    "tesla":        ("Tesla", "테슬라", "자동차"),
    "toyota":       ("Toyota", "토요타", "자동차"),
    "bmw":          ("BMW", "BMW", "자동차"),
    "volkswagen":   ("Volkswagen", "폭스바겐", "자동차"),
    "honda":        ("Honda", "혼다", "자동차"),
    "ford":         ("Ford", "포드", "자동차"),
    # 반도체/IT
    "intel":        ("Intel", "인텔", "반도체/IT"),
    "nvidia":       ("Nvidia", "엔비디아", "반도체/IT"),
    "qualcomm":     ("Qualcomm", "퀄컴", "반도체/IT"),
    # 협업/SaaS
    "zoom":         ("Zoom", "줌", "협업도구"),
    "webex":        ("Webex", "웹엑스", "협업도구"),
    "sap":          ("SAP", "SAP", "기업솔루션"),
    "hubspot":      ("HubSpot", "허브스팟", "기업솔루션"),
    # 여행
    "expedia":      ("Expedia", "익스피디아", "여행"),
    "tripadvisor":  ("Tripadvisor", "트립어드바이저", "여행"),
    # 모빌리티/배달
    "lyft":         ("Lyft", "리프트", "모빌리티"),
    "doordash":     ("DoorDash", "도어대시", "음식배달"),
    # 리테일/패션
    "target":       ("Target", "타겟", "유통/쇼핑"),
    "zara":         ("Zara", "자라", "패션"),
    "uniqlo":       ("Uniqlo", "유니클로", "패션"),
}

SI_CDN_BASE = "https://cdn.simpleicons.org"


def collect_si_global(dry_run=False) -> list[dict]:
    """Simple Icons CDN에서 글로벌 인기 브랜드 수집"""
    data = load_brands_json()
    existing_map = {b["id"]: b for b in data["brands"]}
    added = 0

    print(f"\n🌐 Simple Icons 글로벌 브랜드 수집 ({len(SI_GLOBAL_TARGETS)}개 대상)")

    for si_slug, (name_en, name_ko, category) in SI_GLOBAL_TARGETS.items():
        brand_id = si_slug
        dest = LOGO_DIR / brand_id

        if brand_id in existing_map:
            print(f"  ⏭  {brand_id} (이미 있음)")
            # sources에 SI 없으면 추가
            b = existing_map[brand_id]
            existing_providers = {s["provider"] for s in b.get("sources", [])}
            if "simple-icons" not in existing_providers:
                b.setdefault("sources", []).append(
                    {"provider": "simple-icons", "file": "sources/si.svg", "label": "컬러 심볼"}
                )
                # si.svg도 저장
                si_path = dest / "sources" / "si.svg"
                if not si_path.exists() and not dry_run:
                    _download_si_svg(si_slug, si_path)
            continue

        svg_url = f"{SI_CDN_BASE}/{si_slug}"
        print(f"  🔍 {brand_id} ({name_en})")

        if dry_run:
            continue

        try:
            req = urllib.request.Request(svg_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()

            if b"<svg" not in raw.lower():
                print(f"     ⚠️  SVG 아님")
                continue

            dest.mkdir(parents=True, exist_ok=True)
            # SI의 경우 아이콘 = 로고 역할 → logo.svg로 저장
            (dest / "logo.svg").write_bytes(raw)
            # sources/ 에도 저장
            (dest / "sources").mkdir(exist_ok=True)
            (dest / "sources" / "si.svg").write_bytes(raw)

            brand_entry = {
                "id": brand_id,
                "name_ko": name_ko,
                "name_en": name_en,
                "category": category,
                "domain": "",
                "logo_svg": True,
                "logo_png": False,
                "source": f"simple-icons:{si_slug}",
                "sources": [
                    {"provider": "simple-icons", "file": "sources/si.svg", "label": "컬러 심볼"}
                ],
            }
            data["brands"].append(brand_entry)
            existing_map[brand_id] = brand_entry
            print(f"     ✅ {len(raw)}B")
            added += 1
            time.sleep(0.4)

        except Exception as e:
            print(f"     ❌ {e}")

    if not dry_run and added > 0:
        save_brands_json(data)
        print(f"\n📝 SI 글로벌 완료: +{added}개 추가")

    return []


def _download_si_svg(slug: str, path: Path):
    """SI CDN에서 SVG 다운로드하여 path에 저장"""
    try:
        req = urllib.request.Request(f"{SI_CDN_BASE}/{slug}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    except Exception as e:
        print(f"     ⚠️  SI 다운로드 실패: {e}")


def collect_fa_sources(dry_run=False) -> int:
    """FA brands SVG를 기존 브랜드의 sources/ 폴더에 저장 (신규 브랜드 추가도 포함)"""
    data = load_brands_json()
    existing_map = {b["id"]: b for b in data["brands"]}
    brands_updated = 0
    brands_added = 0

    print(f"\n🎨 Font Awesome brands 소스 수집 ({len(FA_TARGETS)}개 대상)")

    for fa_slug, (name_en, category) in FA_TARGETS.items():
        # brand_id: cc-visa → visa, x-twitter → x-twitter 등
        brand_id = fa_slug.replace("cc-", "")
        sources_dir = LOGO_DIR / brand_id / "sources"

        fa_path = sources_dir / "fa.svg"
        if fa_path.exists():
            print(f"  ⏭  {brand_id} FA (이미 있음)")
            continue

        svg_url = f"{FA_RAW_BASE}/{fa_slug}.svg"
        print(f"  🔍 {brand_id} ← fa/{fa_slug}")

        if dry_run:
            continue

        try:
            req = urllib.request.Request(svg_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as r:
                if r.status != 200:
                    print(f"     ⚠️  {r.status}")
                    continue
                raw = r.read()

            if b"<svg" not in raw.lower():
                print(f"     ⚠️  SVG 태그 없음")
                continue

            sources_dir.mkdir(parents=True, exist_ok=True)
            fa_path.write_bytes(raw)
            print(f"     ✅ fa.svg ({len(raw):,}B)")

            # brands.json: sources 필드 업데이트
            if brand_id in existing_map:
                b = existing_map[brand_id]
                if "sources" not in b:
                    b["sources"] = []
                # 중복 방지
                if not any(s.get("provider") == "font-awesome" for s in b["sources"]):
                    b["sources"].append({"provider": "font-awesome", "file": "sources/fa.svg", "label": "아이콘형"})
                brands_updated += 1
            else:
                # 신규 브랜드로 추가
                new_brand = {
                    "id": brand_id,
                    "name_ko": name_en,
                    "name_en": name_en,
                    "category": category,
                    "domain": "",
                    "logo_svg": True,
                    "source": f"font-awesome:{fa_slug}",
                    "status": "raw",
                    "sources": [{"provider": "font-awesome", "file": "sources/fa.svg", "label": "아이콘형"}],
                }
                data["brands"].append(new_brand)
                existing_map[brand_id] = new_brand
                brands_added += 1
                print(f"     ➕ 신규 브랜드 추가")

            time.sleep(0.2)
        except Exception as e:
            print(f"     ❌ {e}")

    save_brands_json(data)
    print(f"\n📝 FA sources 완료: 기존 {brands_updated}개 업데이트, 신규 {brands_added}개 추가")
    return brands_updated + brands_added


def add_existing_sources(dry_run=False):
    """기존 브랜드에 logo.dev/SI/FA sources 필드 소급 적용"""
    data = load_brands_json()
    updated = 0

    for b in data["brands"]:
        brand_id = b["id"]
        dest = LOGO_DIR / brand_id
        if "sources" not in b:
            b["sources"] = []

        existing_providers = {s["provider"] for s in b["sources"]}

        # logo.dev 소스 감지 (source 필드가 logo.dev: 또는 logo.png만 있는 경우)
        if "logo.dev" not in existing_providers:
            if b.get("source", "").startswith("logo.dev:") or (
                (dest / "logo.png").exists() and not (dest / "logo.svg").exists()
                and not b.get("source", "").startswith(("wikimedia:", "simple-icons:", "font-awesome:"))
            ):
                b["sources"].insert(0, {"provider": "logo.dev", "file": "logo.png", "label": "실물형"})
                updated += 1

        # Wikimedia 소스 감지
        if "wikimedia" not in existing_providers and b.get("source", "").startswith("wikimedia:"):
            b["sources"].append({"provider": "wikimedia", "file": "logo.svg", "label": "공식 SVG"})
            updated += 1

        # Simple Icons 소스 감지
        if "simple-icons" not in existing_providers and b.get("source", "").startswith("simple-icons:"):
            b["sources"].append({"provider": "simple-icons", "file": "logo.svg", "label": "컬러 심볼"})
            updated += 1

        # FA sources/ 폴더 있으면
        if "font-awesome" not in existing_providers and (dest / "sources" / "fa.svg").exists():
            b["sources"].append({"provider": "font-awesome", "file": "sources/fa.svg", "label": "아이콘형"})
            updated += 1

    if not dry_run:
        save_brands_json(data)
    print(f"📝 sources 소급 적용: {updated}개 업데이트")


def main():
    parser = argparse.ArgumentParser(description="한국 브랜드 SVG 자동 수집")
    parser.add_argument("--source", choices=["wiki", "simple", "fa", "sources", "si-global", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", help="다운로드 없이 목록만")
    parser.add_argument("--no-pipeline", action="store_true", help="파이프라인 실행 생략")
    parser.add_argument("--commit",  action="store_true", help="완료 후 git commit + push")
    args = parser.parse_args()

    all_collected = []

    if args.source in ("wiki", "all"):
        results = collect_wikimedia(dry_run=args.dry_run)
        all_collected.extend(results)

    if args.source in ("simple", "all"):
        results = collect_simple_icons(dry_run=args.dry_run)
        all_collected.extend(results)

    if args.source in ("si-global",):
        collect_si_global(dry_run=args.dry_run)
        return

    if args.source in ("fa", "all"):
        collect_fa_sources(dry_run=args.dry_run)

    if args.source == "sources":
        add_existing_sources(dry_run=args.dry_run)
        return

    if args.dry_run:
        print(f"\n📋 수집 예정: {len(all_collected)}개")
        for b in all_collected:
            print(f"  {b['id']}")
        return

    if not all_collected and args.source not in ("fa", "all"):
        print("\n✨ 신규 브랜드 없음")
        return

    # brands.json 업데이트 (wiki/simple 신규분)
    if all_collected:
        data = load_brands_json()
        existing_ids = {b["id"] for b in data["brands"]}
        added = []
        for brand in all_collected:
            if brand["id"] not in existing_ids:
                data["brands"].append(brand)
                existing_ids.add(brand["id"])
                added.append(brand["id"])
        save_brands_json(data)
        print(f"\n📝 brands.json 업데이트: +{len(added)}개")

        # 파이프라인 실행
        if not args.no_pipeline:
            print("\n🔧 파이프라인 실행 중...")
            for brand in all_collected:
                run_pipeline(brand["id"])

    # git commit
    if args.commit:
        print("\n📦 git commit...")
        subprocess.run(["git", "add", "_clients/"], cwd=BASE)
        msg = f"feat: 소스 비교 데이터 추가 (FA brands + sources 필드)"
        subprocess.run(["git", "commit", "-m", msg], cwd=BASE)
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE)
        print("  ✅ push 완료")

    if all_collected:
        print(f"\n✅ 완료: {len(all_collected)}개 수집")


if __name__ == "__main__":
    main()
