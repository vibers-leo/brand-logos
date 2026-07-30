#!/usr/bin/env python3
"""
한국 브랜드 SVG 자동 수집 파이프라인

소스:
  1. Wikimedia Commons — Category:SVG logos of companies of South Korea 등
  2. Simple Icons — 한국 브랜드 필터

실행:
  python3 collect-auto.py                  # 전체 실행
  python3 collect-auto.py --source wiki    # Wikimedia만
  python3 collect-auto.py --source simple  # Simple Icons만
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

    # 한국 관련 키워드
    KR_KEYWORDS = [
        "korea", "korean", "samsung", "lg ", "hyundai", "kia", "sk ", "lotte",
        "kakao", "naver", "coupang", "krafton", "ncsoft", "nexon", "netmarble",
        "hybe", "bighit", "sm entertainment", "yg entertainment", "jyp",
        "posco", "hanwha", "doosan", "lginnotek", "kepco",
        "kb ", "shinhan", "woori", "hana bank", "ibk", "nh ",
        "cj ", "amorepacific", "cosmax", "hugel",
        "krafton", "pearl abyss",
    ]

    collected = []
    for icon in icons:
        title = icon.get("title", "").lower()
        slug  = icon.get("slug", slugify(icon.get("title", "")))

        # 한국 브랜드 감지
        is_kr = any(kw in title for kw in KR_KEYWORDS)
        if not is_kr:
            continue

        brand_id = slug or slugify(icon["title"])
        if brand_id in existing:
            print(f"  ⏭  {brand_id} (이미 있음)")
            continue

        hex_color = icon.get("hex", "000000")
        print(f"  🔍 {brand_id} — {icon['title']} (#{hex_color})")

        if dry_run:
            collected.append({"id": brand_id, "title": icon["title"]})
            existing.add(brand_id)
            continue

        # Simple Icons SVG URL
        svg_url = f"https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/{slug}.svg"
        try:
            result = download_svg(brand_id, svg_url, f"{slug}.svg")
            if result:
                result["source"] = f"simple-icons:{slug}"
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


def main():
    parser = argparse.ArgumentParser(description="한국 브랜드 SVG 자동 수집")
    parser.add_argument("--source",  choices=["wiki", "simple", "all"], default="all")
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

    if args.dry_run:
        print(f"\n📋 수집 예정: {len(all_collected)}개")
        for b in all_collected:
            print(f"  {b['id']}")
        return

    if not all_collected:
        print("\n✨ 신규 브랜드 없음")
        return

    # brands.json 업데이트
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
    if args.commit and added:
        print("\n📦 git commit...")
        subprocess.run(["git", "add", "_clients/"], cwd=BASE)
        msg = f"feat: 자동 수집 +{len(added)}개 브랜드 ({', '.join(added[:5])}{'...' if len(added)>5 else ''})"
        subprocess.run(["git", "commit", "-m", msg], cwd=BASE)
        subprocess.run(["git", "push", "origin", "main"], cwd=BASE)
        print("  ✅ push 완료")

    print(f"\n✅ 완료: {len(all_collected)}개 수집")


if __name__ == "__main__":
    main()
