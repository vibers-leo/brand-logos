#!/usr/bin/env python3
"""
PNG-only 브랜드 → SVG 업그레이드
1순위: Simple Icons CDN (cdn.simpleicons.org/{slug})
2순위: Wikimedia Commons (이미 수집된 공공기관 경로 재활용)
3순위: Brand.dev API

실행: python3 scripts/upgrade-png-to-svg.py
"""

import json
import os
import re
import subprocess
import time
import unicodedata
from pathlib import Path

CLIENTS = Path(__file__).parent.parent / "_clients"
BRANDS_JSON = CLIENTS / "brands.json"
SLUGS_FILE = "/tmp/simple-icons-slugs.txt"
WIKIMEDIA_PROXY = "https://wikimedia-proxy.yahwaedge.workers.dev"

# Simple Icons slug 정규화 함수 (공식 알고리즘)
def to_si_slug(title: str) -> str:
    """name_en → Simple Icons slug 변환"""
    s = title.lower().strip()
    # 특수문자 제거, 공백 제거
    s = re.sub(r'[^a-z0-9]', '', s)
    return s

def normalize_variants(name_en: str) -> list[str]:
    """여러 slug 후보 생성"""
    base = name_en.lower().strip()
    candidates = set()

    # 1. 직접 소문자
    candidates.add(re.sub(r'[^a-z0-9]', '', base))

    # 2. 공백을 대시로 (일부 SI는 이런 식)
    candidates.add(re.sub(r'\s+', '-', base).rstrip('-'))
    candidates.add(re.sub(r'[^a-z0-9-]', '', re.sub(r'\s+', '-', base)))

    # 3. 괄호 안 내용 제거 후
    without_paren = re.sub(r'\(.*?\)', '', base).strip()
    candidates.add(re.sub(r'[^a-z0-9]', '', without_paren))

    # 4. 첫 단어만
    first_word = base.split()[0] if ' ' in base else base
    candidates.add(re.sub(r'[^a-z0-9]', '', first_word))

    # 5. 약어 추출 (e.g. "Korea Fair Trade Commission" → "kftc")
    words = re.findall(r'\b[a-z]', base)
    if len(words) >= 2:
        candidates.add(''.join(words))

    return [c for c in candidates if c]


def download_svg(url: str, timeout: int = 15) -> bytes | None:
    """URL에서 SVG 다운로드. 실패 시 None 반환."""
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), url],
            capture_output=True, timeout=timeout + 5
        )
        if r.returncode == 0 and r.stdout:
            content = r.stdout
            if b"<svg" in content or b"<?xml" in content:
                return content
    except Exception as e:
        pass
    return None


def fetch_via_proxy(url: str) -> bytes | None:
    """Wikimedia CF Worker 프록시 경유 다운로드"""
    import urllib.parse
    proxy_url = f"{WIKIMEDIA_PROXY}?url={urllib.parse.quote(url, safe='')}"
    return download_svg(proxy_url)


def try_simple_icons(name_en: str, si_slug_set: set) -> tuple[str | None, bytes | None]:
    """Simple Icons CDN에서 SVG 탐색. (slug, content) 반환"""
    candidates = normalize_variants(name_en)
    for slug in candidates:
        if slug in si_slug_set:
            url = f"https://cdn.simpleicons.org/{slug}"
            content = download_svg(url)
            if content:
                return slug, content
    return None, None


def try_wikimedia_brand(brand: dict) -> bytes | None:
    """Wikimedia Commons에서 브랜드 로고 탐색 (공공기관 등)"""
    import hashlib, urllib.parse
    name_en = brand.get("name_en", "")
    name_ko = brand.get("name_ko", "")

    # 일반적인 Commons 파일명 패턴 시도
    patterns = [
        f"File:{name_en} logo.svg",
        f"File:Logo of {name_en}.svg",
        f"File:{name_en} Logo.svg",
        f"File:{name_en.replace(' ', '_')}_logo.svg",
    ]
    for pattern in patterns[:2]:  # 너무 많이 시도하면 느림
        filename = pattern.replace("File:", "").replace(" ", "_")
        h = hashlib.md5(filename.encode()).hexdigest()
        encoded = urllib.parse.quote(filename, safe="")
        url = f"https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[0:2]}/{encoded}"
        content = fetch_via_proxy(url)
        if content:
            return content
    return None


def load_si_slugs() -> set:
    """Simple Icons slug 목록 로드 (없으면 GitHub API로 취득)"""
    if os.path.exists(SLUGS_FILE):
        with open(SLUGS_FILE) as f:
            slugs = {l.strip() for l in f if l.strip()}
        print(f"Simple Icons slug 로드: {len(slugs)}개")
        return slugs

    print("Simple Icons slug 목록 다운로드 중...")
    r = subprocess.run([
        "curl", "-sL",
        "https://api.github.com/repos/simple-icons/simple-icons/git/trees/HEAD?recursive=1",
        "--max-time", "30"
    ], capture_output=True, timeout=40)
    tree = json.loads(r.stdout)
    svgs = [item["path"] for item in tree.get("tree", [])
            if item["path"].startswith("icons/") and item["path"].endswith(".svg")]
    slugs = {s.replace("icons/", "").replace(".svg", "") for s in svgs}
    with open(SLUGS_FILE, "w") as f:
        f.write("\n".join(sorted(slugs)))
    print(f"Simple Icons slug 취득: {len(slugs)}개")
    return slugs


def main():
    with open(BRANDS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    brands = data["brands"] if "brands" in data else data

    # PNG-only 브랜드 추출
    png_only = [
        b for b in brands
        if (CLIENTS / b["id"] / "logo.png").exists()
        and not (CLIENTS / b["id"] / "logo.svg").exists()
    ]
    print(f"PNG-only 브랜드: {len(png_only)}개")

    si_slugs = load_si_slugs()

    upgraded = 0
    failed = []

    for i, brand in enumerate(png_only):
        bid = brand["id"]
        name_en = brand.get("name_en", "")
        name_ko = brand.get("name_ko", "")
        cat = brand.get("category", "")

        print(f"\n[{i+1}/{len(png_only)}] {bid} ({name_en})", end=" ")

        content = None
        source = None

        # 1순위: Simple Icons
        if name_en:
            slug, content = try_simple_icons(name_en, si_slugs)
            if content:
                source = f"simple-icons/{slug}"

        # 2순위: Wikimedia (공공기관)
        if not content and cat in ("공공·기관", "공공/기관"):
            content = try_wikimedia_brand(brand)
            if content:
                source = "wikimedia-commons"

        if content:
            svg_path = CLIENTS / bid / "logo.svg"
            svg_path.write_bytes(content)

            # brands.json 업데이트
            for b in (data["brands"] if "brands" in data else data):
                if b["id"] == bid:
                    b["has_svg"] = True
                    if source:
                        b["svg_source"] = source
                    break

            print(f"✅ ({len(content):,}B) [{source}]")
            upgraded += 1
        else:
            print(f"❌ 못찾음")
            failed.append(bid)

        time.sleep(0.3)

    # 저장
    with open(BRANDS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n완료: {upgraded}개 업그레이드, {len(failed)}개 실패")
    if failed:
        print(f"실패 목록 ({len(failed)}개):")
        for fid in failed[:20]:
            print(f"  {fid}")
        if len(failed) > 20:
            print(f"  ...외 {len(failed)-20}개")


if __name__ == "__main__":
    main()
