#!/usr/bin/env python3
"""
위키미디어 SVG 로고 수집 스크립트
용도: Wikipedia 파일 페이지 URL 또는 파일명으로 SVG를 DB에 저장

사용법:
  # 단일 브랜드
  python3 wiki-fetch.py --brand bts --file "BTS_logo.svg"

  # 위키피디아 URL에서 바로
  python3 wiki-fetch.py --brand apec --url "https://ko.wikipedia.org/wiki/파일:APEC_Logo.svg"

  # 일괄 처리 (brand:파일명 형식)
  python3 wiki-fetch.py --batch targets.txt

  # DB 전체 검증
  python3 wiki-fetch.py --validate
"""

import argparse, json, os, sys, time, urllib.request, urllib.parse

LOGO_DIR = os.path.expanduser("~/Desktop/macminim4/brand-logos/_clients")
BRANDS_JSON = os.path.join(LOGO_DIR, "brands.json")
UA = "VibersLogoDB/1.0 (vibers.leo@gmail.com)"


def wiki_api_url(filename: str, lang="ko") -> str:
    """위키미디어 API로 파일의 실제 업로드 URL을 가져온다."""
    api = f"https://{lang}.wikipedia.org/w/api.php?action=query&titles=File:{urllib.parse.quote(filename)}&prop=imageinfo&iiprop=url&format=json"
    req = urllib.request.Request(api, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    pages = data["query"]["pages"]
    page = next(iter(pages.values()))
    infos = page.get("imageinfo", [])
    if not infos:
        # ko에 없으면 commons에서 재시도
        if lang != "commons":
            return wiki_api_url(filename, "commons")
        raise ValueError(f"이미지 정보 없음: {filename}")
    return infos[0]["url"]


def url_from_wiki_page(page_url: str) -> tuple[str, str]:
    """ko.wikipedia.org/wiki/파일:XXX.svg 형태 URL에서 (filename, download_url) 반환."""
    # URL 파싱: 파일명 추출
    path = urllib.parse.urlparse(page_url).path  # /wiki/파일:XXX.svg
    encoded_filename = path.split("파일:")[-1] if "파일:" in path else path.split("File:")[-1]
    filename = urllib.parse.unquote(encoded_filename)
    download_url = wiki_api_url(filename)
    return filename, download_url


def download_and_save(brand_id: str, download_url: str) -> bool:
    """SVG 다운로드 → 검증 → 저장. 성공하면 True."""
    req = urllib.request.Request(download_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()

    # UTF-16 BOM 처리
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        encoding = "utf-16-le" if raw[:2] == b'\xff\xfe' else "utf-16-be"
        content = raw.decode(encoding).encode("utf-8")
    else:
        content = raw

    # 검증
    issues = []
    if b"<svg" not in content and b"<SVG" not in content:
        issues.append("SVG태그없음")
    if b"DOCTYPE html" in content:
        issues.append("HTML에러페이지")
    if b"data:image/" in content:
        issues.append("base64비트맵내장")
    if b"<image" in content:
        issues.append("image태그")

    if issues:
        print(f"  ⚠️  검증 실패: {', '.join(issues)}")
        return False

    dest_dir = os.path.join(LOGO_DIR, brand_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "logo.svg")
    with open(dest, "wb") as f:
        f.write(content)
    print(f"  ✅ 저장: {dest} ({len(content):,}B)")
    return True


def validate_all():
    """DB 전체 검증."""
    good, bad = [], []
    skip = {"brands.json", "preview_grid.png", "preview_official.png"}
    for brand in sorted(os.listdir(LOGO_DIR)):
        if brand in skip:
            continue
        svg = os.path.join(LOGO_DIR, brand, "logo.svg")
        if not os.path.isfile(svg):
            continue
        with open(svg, "rb") as f:
            c = f.read()
        is_ok = (b"<svg" in c and b"data:image/" not in c
                 and b"<image" not in c and b"DOCTYPE html" not in c)
        (good if is_ok else bad).append((brand, len(c)))

    print(f"✅ 벡터 SVG ({len(good)}개):")
    for b, s in good:
        print(f"   {b:<28} {s:>8,}B")
    if bad:
        print(f"\n❌ 불량 ({len(bad)}개):")
        for b, s in bad:
            print(f"   {b:<28} {s:>8,}B")
    print(f"\n합계: {len(good) + len(bad)}개 (✅{len(good)} / ❌{len(bad)})")


def main():
    parser = argparse.ArgumentParser(description="Wikimedia SVG 로고 수집")
    parser.add_argument("--brand",    help="저장할 브랜드 ID (영문 소문자)")
    parser.add_argument("--file",     help="위키미디어 파일명 (예: BTS_logo.svg)")
    parser.add_argument("--url",      help="ko.wikipedia.org/wiki/파일:XXX 형태 URL")
    parser.add_argument("--batch",    help="일괄 처리 파일 (brand:파일명 한 줄씩)")
    parser.add_argument("--validate", action="store_true", help="DB 전체 검증")
    args = parser.parse_args()

    if args.validate:
        validate_all()
        return

    if args.batch:
        with open(args.batch) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        for line in lines:
            brand_id, filename = line.split(":", 1)
            print(f"\n[{brand_id}] {filename}")
            try:
                url = wiki_api_url(filename.strip())
                download_and_save(brand_id.strip(), url)
            except Exception as e:
                print(f"  ❌ {e}")
            time.sleep(1)
        return

    if args.url:
        if not args.brand:
            print("--brand 필요"); sys.exit(1)
        print(f"[{args.brand}] {args.url}")
        _, download_url = url_from_wiki_page(args.url)
        download_and_save(args.brand, download_url)
        return

    if args.file:
        if not args.brand:
            print("--brand 필요"); sys.exit(1)
        print(f"[{args.brand}] {args.file}")
        url = wiki_api_url(args.file)
        download_and_save(args.brand, url)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
