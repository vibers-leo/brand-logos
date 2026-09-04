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


# 저장 가드 — 확장자와 내용이 다르면 쓰지 않는다 (404 HTML 이 logo.svg 로
# 저장되던 사고 재발 방지). scripts/ 밖에서도 import 되도록 경로를 넣는다.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent / "scripts"))
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from assetguard import safe_write

import argparse, json, os, re, subprocess, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
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


def _open_backoff(req, timeout=15, tries=3):
    """429(봇 과속) 를 만나면 60초 쉬고 다시 시도한다.

    ⚠️ 2026-09-04 daily-collect 로그에 429 가 하루 232회. 재시도가 없어서 그 회차의
       다운로드가 전부 실패했고, 10일간 신규 수집이 하루 0~1건이었다.
       위키미디어는 초당 1회 안쪽을 권한다 — 간격도 0.3s→1.0s 로 늦췄다.
    """
    for i in range(tries):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                wait = 60 * (i + 1)
                print(f"      ⏳ 429 — {wait}s 대기 후 재시도", flush=True)
                time.sleep(wait); continue
            raise


def wiki_api(params: dict, site="commons.wikimedia.org") -> dict:
    params["format"] = "json"
    url = f"https://{site}/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with _open_backoff(req, timeout=15) as r:
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
                    time.sleep(1.0)  # 위키미디어 봇 한도 — 0.3s(초당 3.3회)는 429 로 하루 232회 차단됐다(2026-09-04)
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
            time.sleep(1.0)

    return collected


def download_svg(brand_id: str, url: str, filename: str) -> dict | None:
    """SVG 다운로드 → 검증 → 저장 → brands.json 항목 반환"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with _open_backoff(req, timeout=20) as r:
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
    safe_write(svg_path, content)

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
        with _open_backoff(req, timeout=30) as r:
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
                time.sleep(1.0)
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
            safe_write(dest / "logo.svg", raw)
            # sources/ 에도 저장
            (dest / "sources").mkdir(exist_ok=True)
            safe_write(dest / "sources" / "si.svg", raw)

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
        safe_write(path, raw)
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
            safe_write(fa_path, raw)
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


ICONIFY_API = "https://api.iconify.design"

# Iconify logos 세트 variant suffix → sources label 매핑
ICONIFY_VARIANT_LABELS = {
    "-icon":      "아이콘형",
    "-wordmark":  "워드마크형",
    "-color":     "컬러 심볼",
    "-dark":      "다크 버전",
    "-light":     "라이트 버전",
}

def collect_iconify(dry_run=False):
    """Iconify logos 세트 전체 수집 (신규 브랜드 추가 + 기존 sources 층위 추가)"""
    data = load_brands_json()
    existing_map = {b["id"]: b for b in data["brands"]}
    added = 0
    layered = 0

    print("\n🎨 Iconify logos 세트 수집 중...")
    # 1. 전체 아이콘 목록 로드
    try:
        req = urllib.request.Request(f"{ICONIFY_API}/collection?prefix=logos",
                                     headers={"User-Agent": UA})
        with _open_backoff(req, timeout=20) as r:
            meta = json.loads(r.read())
    except Exception as e:
        print(f"  ❌ 목록 로드 실패: {e}")
        return

    all_icons = list(meta.get("uncategorized", []))
    for items in meta.get("categories", {}).values():
        all_icons.extend(items)
    all_icons = sorted(set(all_icons))
    print(f"  총 {len(all_icons)}개 아이콘")

    for slug in all_icons:
        # variant 분리 (adobe-illustrator-icon → base=adobe-illustrator, variant=-icon)
        variant_suffix = ""
        base_id = slug
        for sfx in ICONIFY_VARIANT_LABELS:
            if slug.endswith(sfx):
                base_id = slug[: -len(sfx)]
                variant_suffix = sfx
                break

        label = ICONIFY_VARIANT_LABELS.get(variant_suffix, "컬러 심볼")
        provider_key = f"iconify:{slug}"

        if dry_run:
            if base_id in existing_map:
                providers = {s["provider"] for s in existing_map[base_id].get("sources", [])}
                if provider_key not in providers:
                    print(f"  [layer] {base_id} ← logos/{slug}")
            else:
                print(f"  [new]   {slug}")
            continue

        svg_url = f"{ICONIFY_API}/logos/{slug}.svg"
        try:
            req = urllib.request.Request(svg_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
            if b"<svg" not in raw[:300].lower():
                continue
        except Exception as e:
            continue

        dest = LOGO_DIR / base_id
        dest.mkdir(parents=True, exist_ok=True)
        icon_dir = dest / "sources" / "iconify"
        icon_dir.mkdir(parents=True, exist_ok=True)
        svg_file = icon_dir / f"{slug}.svg"
        safe_write(svg_file, raw)

        if base_id in existing_map:
            # 기존 브랜드 → sources 층위 추가
            b = existing_map[base_id]
            existing_providers = {s["provider"] for s in b.get("sources", [])}
            if provider_key not in existing_providers:
                b.setdefault("sources", []).append({
                    "provider": provider_key,
                    "file": f"sources/iconify/{slug}.svg",
                    "label": label,
                })
                layered += 1
                print(f"  ➕ [layer] {base_id} ← logos/{slug} ({label})")
        else:
            # 신규 브랜드 추가
            # base slug의 기본 SVG 설정 (variant 없는 것 우선)
            if not variant_suffix:
                safe_write(dest / "logo.svg", raw)
                # PNG 생성
                try:
                    import cairosvg
                    cairosvg.svg2png(url=str(dest / "logo.svg"),
                                     write_to=str(dest / "logo.png"),
                                     output_width=400, output_height=400,
                                     background_color="white")
                    has_png = True
                except Exception:
                    has_png = False

                brand_entry = {
                    "id": base_id,
                    "name_ko": base_id.replace("-", " ").title(),
                    "name_en": base_id.replace("-", " ").title(),
                    "category": "전자/IT",
                    "domain": "",
                    "logo_svg": True,
                    "logo_png": has_png,
                    "source": f"iconify:{slug}",
                    "sources": [{
                        "provider": provider_key,
                        "file": f"sources/iconify/{slug}.svg",
                        "label": label,
                    }],
                }
                data["brands"].append(brand_entry)
                existing_map[base_id] = brand_entry
                added += 1
                print(f"  ✅ [new]   {base_id}")

        time.sleep(0.15)

    if not dry_run:
        save_brands_json(data)
    print(f"\n📝 Iconify 완료: 신규 {added}개, 층위 추가 {layered}개")


# ── Devicons ──────────────────────────────────────────────────────────
DEVICONS_RAW = "https://raw.githubusercontent.com/devicons/devicon/master"

def collect_devicons(dry_run=False):
    """Devicons에서 테크 브랜드 SVG 수집 (신규 + sources 층위)"""
    data = load_brands_json()
    existing_map = {b["id"]: b for b in data["brands"]}
    added = 0
    layered = 0

    print("\n⚙️  Devicons 수집 중...")
    # devicon.json 메타데이터
    try:
        req = urllib.request.Request(f"{DEVICONS_RAW}/devicon.json",
                                     headers={"User-Agent": UA})
        with _open_backoff(req, timeout=20) as r:
            icons_meta = json.loads(r.read())
    except Exception as e:
        print(f"  ❌ devicon.json 로드 실패: {e}")
        return

    print(f"  총 {len(icons_meta)}개 아이콘")

    for icon in icons_meta:
        name = icon["name"]          # e.g. "react"
        versions = icon.get("versions", {})
        svg_versions = versions.get("svg", [])   # ["original", "plain", "colored"]

        if not svg_versions:
            continue

        # 우선순위: colored > original > plain
        preferred = next((v for v in ("colored", "original", "plain") if v in svg_versions), svg_versions[0])
        slug = f"{name}-{preferred}"
        provider_key = f"devicons:{slug}"

        if dry_run:
            if name in existing_map:
                print(f"  [layer] {name} ← devicons/{slug}")
            else:
                print(f"  [new]   {name}")
            continue

        svg_url = f"{DEVICONS_RAW}/icons/{name}/{slug}.svg"
        try:
            req = urllib.request.Request(svg_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
            if b"<svg" not in raw[:300].lower():
                continue
        except Exception:
            continue

        dest = LOGO_DIR / name
        dest.mkdir(parents=True, exist_ok=True)
        icon_dir = dest / "sources" / "devicons"
        icon_dir.mkdir(parents=True, exist_ok=True)
        svg_file = icon_dir / f"{slug}.svg"
        safe_write(svg_file, raw)

        if name in existing_map:
            b = existing_map[name]
            existing_providers = {s["provider"] for s in b.get("sources", [])}
            if provider_key not in existing_providers:
                b.setdefault("sources", []).append({
                    "provider": provider_key,
                    "file": f"sources/devicons/{slug}.svg",
                    "label": "컬러 심볼",
                })
                layered += 1
                print(f"  ➕ [layer] {name} ← {slug}")
        else:
            safe_write(dest / "logo.svg", raw)
            try:
                import cairosvg
                cairosvg.svg2png(url=str(dest / "logo.svg"),
                                 write_to=str(dest / "logo.png"),
                                 output_width=400, output_height=400,
                                 background_color="white")
                has_png = True
            except Exception:
                has_png = False

            tags = icon.get("tags", [])
            brand_entry = {
                "id": name,
                "name_ko": name.title(),
                "name_en": name.title(),
                "category": "개발도구",
                "domain": "",
                "logo_svg": True,
                "logo_png": has_png,
                "source": f"devicons:{slug}",
                "sources": [{
                    "provider": provider_key,
                    "file": f"sources/devicons/{slug}.svg",
                    "label": "컬러 심볼",
                }],
            }
            data["brands"].append(brand_entry)
            existing_map[name] = brand_entry
            added += 1
            print(f"  ✅ [new]   {name}")

        time.sleep(0.1)

    if not dry_run:
        save_brands_json(data)
    print(f"\n📝 Devicons 완료: 신규 {added}개, 층위 추가 {layered}개")


# ── WorldVectorLogo (gilbarbara/logos GitHub 레포) ─────────────────────
WVL_RAW = "https://raw.githubusercontent.com/gilbarbara/logos/main/logos"
WVL_API = "https://api.github.com/repos/gilbarbara/logos/contents/logos"

def collect_worldvector(dry_run=False):
    """gilbarbara/logos (WorldVectorLogo 원본 레포) SVG 수집 — logos.json 기반"""
    data = load_brands_json()
    existing_map = {b["id"]: b for b in data["brands"]}
    added = 0
    layered = 0

    print("\n🌍 WorldVectorLogo (gilbarbara/logos) 수집 중...")
    # logos.json으로 파일 목록 (GitHub API rate limit 없음)
    try:
        req = urllib.request.Request(
            "https://raw.githubusercontent.com/gilbarbara/logos/main/logos.json",
            headers={"User-Agent": UA},
        )
        with _open_backoff(req, timeout=20) as r:
            logos_meta = json.loads(r.read())
    except Exception as e:
        print(f"  ❌ logos.json 로드 실패: {e}")
        return

    # shortname → files 매핑으로 전개
    svg_entries = []  # (base_id, fname, name_en, url)
    for entry in logos_meta:
        base_id = entry["shortname"]
        name_en = entry["name"]
        for fname in entry.get("files", []):
            if fname.endswith(".svg"):
                svg_entries.append((base_id, fname, name_en))

    print(f"  총 {len(svg_entries)}개 SVG (브랜드 {len(logos_meta)}개)")

    for base_id, fname, name_en in svg_entries:
        slug = fname[:-4]           # e.g. "react"
        provider_key = f"wvl:{slug}"

        # variant 처리 (active-campaign-icon.svg → base=active-campaign, label=아이콘형)
        label = "컬러 심볼"
        for sfx, lbl in [("-icon","아이콘형"), ("-wordmark","워드마크형"), ("-color","컬러 심볼")]:
            if slug.endswith(sfx):
                label = lbl
                break

        if dry_run:
            if base_id in existing_map:
                print(f"  [layer] {base_id} ← wvl/{slug}")
            else:
                print(f"  [new]   {base_id}")
            continue

        svg_url = f"{WVL_RAW}/{fname}"
        try:
            req = urllib.request.Request(svg_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
            if b"<svg" not in raw[:300].lower():
                continue
        except Exception:
            continue

        dest = LOGO_DIR / base_id
        dest.mkdir(parents=True, exist_ok=True)
        wvl_dir = dest / "sources" / "wvl"
        wvl_dir.mkdir(parents=True, exist_ok=True)
        (wvl_dir / fname).write_bytes(raw)

        if base_id in existing_map:
            b = existing_map[base_id]
            existing_providers = {s["provider"] for s in b.get("sources", [])}
            if provider_key not in existing_providers:
                b.setdefault("sources", []).append({
                    "provider": provider_key,
                    "file": f"sources/wvl/{fname}",
                    "label": label,
                })
                layered += 1
                print(f"  ➕ [layer] {base_id} ← wvl/{slug}")
        else:
            if not any(slug.endswith(sfx) for sfx in ("-icon", "-wordmark", "-color")):
                safe_write(dest / "logo.svg", raw)
                try:
                    import cairosvg
                    cairosvg.svg2png(url=str(dest / "logo.svg"),
                                     write_to=str(dest / "logo.png"),
                                     output_width=400, output_height=400,
                                     background_color="white")
                    has_png = True
                except Exception:
                    has_png = False

                brand_entry = {
                    "id": base_id,
                    "name_ko": name_en,
                    "name_en": name_en,
                    "category": "전자/IT",
                    "domain": "",
                    "logo_svg": True,
                    "logo_png": has_png,
                    "source": f"wvl:{slug}",
                    "sources": [{
                        "provider": provider_key,
                        "file": f"sources/wvl/{fname}",
                        "label": label,
                    }],
                }
                data["brands"].append(brand_entry)
                existing_map[base_id] = brand_entry
                added += 1
                print(f"  ✅ [new]   {base_id} ({name_en})")

        time.sleep(0.1)

    if not dry_run:
        save_brands_json(data)
    print(f"\n📝 WorldVectorLogo 완료: 신규 {added}개, 층위 추가 {layered}개")


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


def apply_votes(dry_run=False):
    """
    Firestore logo_votes 컬렉션을 읽어:
    - swap_pending=True 인 브랜드의 swap_target 파일을 logo.svg 또는 logo.png로 교체
    - 처리 후 swap_pending=False 로 초기화
    """
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        print("❌ firebase-admin 미설치: pip install firebase-admin")
        return

    # 서비스 계정 키 (ai-recipe .env.local에서 추출 후 저장)
    sa_path = BASE / ".firebase-sa.json"
    if not sa_path.exists():
        # 환경변수에서 JSON 읽기 시도
        import os, json as _json
        sa_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY", "")
        if not sa_str:
            print("❌ .firebase-sa.json 없고 FIREBASE_SERVICE_ACCOUNT_KEY 환경변수도 없음")
            print("  방법: ai-recipe/.env.local의 FIREBASE_SERVICE_ACCOUNT_KEY 값을 .firebase-sa.json으로 저장")
            return
        sa_path.write_text(sa_str)

    if not firebase_admin._apps:
        cred = credentials.Certificate(str(sa_path))
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    votes_col = db.collection("logo_votes")
    docs = votes_col.where("swap_pending", "==", True).stream()

    data = load_brands_json()
    brand_map = {b["id"]: b for b in data["brands"]}
    changed = 0

    for doc_snap in docs:
        brand_id = doc_snap.id
        doc_data = doc_snap.to_dict()
        target_file = doc_data.get("swap_target", "")

        if not target_file:
            print(f"  ⚠ {brand_id}: swap_target 없음, 건너뜀")
            continue

        brand_dir = LOGO_DIR / brand_id
        src = brand_dir / target_file
        if not src.exists():
            print(f"  ❌ {brand_id}: {target_file} 파일 없음")
            continue

        if dry_run:
            print(f"  [DRY] {brand_id}: {target_file} → logo.{'svg' if target_file.endswith('.svg') else 'png'}")
            continue

        import shutil
        is_svg = target_file.endswith(".svg")

        # 기존 logo.svg/logo.png 백업
        dest = brand_dir / ("logo.svg" if is_svg else "logo.png")
        if dest.exists():
            shutil.copy2(dest, brand_dir / f"logo.bak.{dest.suffix[1:]}")

        shutil.copy2(src, dest)
        print(f"  ✅ {brand_id}: {target_file} → {dest.name} 교체 완료")

        # brands.json source 필드 업데이트
        if brand_id in brand_map:
            b = brand_map[brand_id]
            # 교체된 파일에 해당하는 sources 엔트리를 index 0으로 이동
            if b.get("sources"):
                idx = next((i for i, s in enumerate(b["sources"]) if s["file"] == target_file), None)
                if idx is not None and idx > 0:
                    b["sources"].insert(0, b["sources"].pop(idx))
            if is_svg:
                b["logo_svg"] = True
            else:
                b["logo_png"] = True

        # PNG 재생성 (SVG 교체 시)
        if is_svg:
            try:
                import cairosvg
                from PIL import Image
                import io
                svg_data = dest.read_bytes()
                png_data = cairosvg.svg2png(bytestring=svg_data, output_width=400, output_height=400)
                img = Image.open(io.BytesIO(png_data)).convert("RGBA")
                bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                bg.convert("RGB").save(brand_dir / "logo.png")
                print(f"    PNG 재생성: {brand_id}/logo.png")
            except Exception as e:
                print(f"    PNG 재생성 실패: {e}")

        # Firestore swap_pending 초기화
        votes_col.document(brand_id).update({
            "swap_pending": False,
            "swap_target": None,
            "applied_at": firestore.SERVER_TIMESTAMP,
        })
        changed += 1

    if changed == 0 and not dry_run:
        print("  교체 대기 중인 브랜드 없음")
    else:
        save_brands_json(data)
        print(f"\n✅ apply-votes 완료: {changed}개 교체")


def main():
    parser = argparse.ArgumentParser(description="한국 브랜드 SVG 자동 수집")
    parser.add_argument("--source", choices=["wiki", "simple", "fa", "sources", "si-global", "iconify", "devicons", "worldvector", "apply-votes", "all"], default="all")
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

    if args.source in ("iconify",):
        collect_iconify(dry_run=args.dry_run)
        return

    if args.source in ("devicons",):
        collect_devicons(dry_run=args.dry_run)
        return

    if args.source in ("worldvector",):
        collect_worldvector(dry_run=args.dry_run)
        return

    if args.source == "sources":
        add_existing_sources(dry_run=args.dry_run)
        return

    if args.source == "apply-votes":
        print("🔄 Firestore 투표 결과 적용 중...")
        apply_votes(dry_run=args.dry_run)
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
        # ⚠️ 예전엔 반환값을 안 보고 무조건 "push 완료"를 찍었다. 이 잡은 5시간
        #    돌기 때문에 그 사이 사람이 푸시하면 'fetch first' 로 거부되는데,
        #    로그에는 성공으로 남아 수집분이 사라진 걸 아무도 몰랐다.
        #    2026-08-27 에 'abd' 1건이 그렇게 유실됐다(로그는 push 완료).
        subprocess.run(["git", "add", "_clients/"], cwd=BASE, check=True)
        msg = "feat: 소스 비교 데이터 추가 (FA brands + sources 필드)"
        c = subprocess.run(["git", "commit", "-m", msg], cwd=BASE,
                           capture_output=True, text=True)
        if c.returncode != 0:
            if "nothing to commit" in (c.stdout + c.stderr):
                print("  변경 없음 — 커밋 생략")
                return
            print(f"  ❌ commit 실패\n{c.stdout[-400:]}{c.stderr[-400:]}")
            raise SystemExit(1)
        r = subprocess.run(["git", "push", "origin", "main"], cwd=BASE,
                           capture_output=True, text=True)
        if r.returncode != 0:
            # 여기서 죽이지 않는다 — 뒤 파이프라인이 만든 산출물까지 버려진다.
            # 커밋은 로컬에 남아 있고, 워크플로 끝의 '변형 산출물 커밋' 단계가
            # rebase 로 따라잡아 다시 올린다.
            print(f"  ⚠️ push 거부 (뒤 커밋 단계가 rebase 로 재시도한다)\n"
                  f"{r.stderr[-400:]}")
        else:
            print("  ✅ push 완료")

    if all_collected:
        print(f"\n✅ 완료: {len(all_collected)}개 수집")


if __name__ == "__main__":
    main()
