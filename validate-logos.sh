#!/usr/bin/env python3
"""
브랜드 로고 DB 검증 스크립트
실행: python3 ~/Desktop/macminim4/brand-logos/validate-logos.sh
"""

import os, sys, hashlib

LOGO_DIR = os.path.expanduser("~/Desktop/macminim4/brand-logos/_clients")

SKIP = {"brands.json", "preview_grid.png", "preview_official.png"}

good, bad, missing = [], [], []
file_hashes = {}  # MD5 → [brand_list] 중복 감지

for brand in sorted(os.listdir(LOGO_DIR)):
    if brand in SKIP:
        continue
    svg_path = os.path.join(LOGO_DIR, brand, "logo.svg")
    if not os.path.isfile(svg_path):
        missing.append(brand)
        continue

    with open(svg_path, "rb") as f:
        content = f.read()

    size = len(content)
    md5 = hashlib.md5(content).hexdigest()
    file_hashes.setdefault(md5, []).append(brand)

    issues = []
    if b"<svg" not in content and b"<SVG" not in content:
        issues.append("SVG태그없음")
    if b"DOCTYPE html" in content:
        issues.append("HTML에러페이지")
    if b"data:image/" in content:
        issues.append("base64비트맵내장")
    if b"<image" in content:
        issues.append("image태그(비트맵)")
    if size > 150_000:
        issues.append(f"파일과대({size//1024}KB)")

    if issues:
        bad.append((brand, size, issues))
    else:
        good.append((brand, size))

# 중복 감지
duplicates = {k: v for k, v in file_hashes.items() if len(v) > 1}

# 결과 출력
print("=" * 60)
print(f"✅ 사용 가능 ({len(good)}개)")
print("=" * 60)
for b, s in good:
    print(f"  {b:<28} {s:>7}B")

print(f"\n{'=' * 60}")
print(f"❌ 사용 불가 ({len(bad)}개)")
print("=" * 60)
for b, s, issues in bad:
    print(f"  {b:<28} {s:>7}B  ← {', '.join(issues)}")

if missing:
    print(f"\n{'=' * 60}")
    print(f"⚪ 파일 없음 ({len(missing)}개)")
    print("=" * 60)
    for b in missing:
        print(f"  {b}")

if duplicates:
    print(f"\n{'=' * 60}")
    print(f"⚠️  중복 파일 ({len(duplicates)}건)")
    print("=" * 60)
    for md5, brands in duplicates.items():
        print(f"  동일 내용: {', '.join(brands)}")

print(f"\n요약: ✅{len(good)} / ❌{len(bad)} / ⚪{len(missing)} / 중복{len(duplicates)}건")
if bad:
    sys.exit(1)
