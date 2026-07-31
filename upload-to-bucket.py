#!/usr/bin/env python3
"""
brand-logos → NCP vibers-bucket 업로드
경로: brand-logos/{brand_id}/{filename}

사용:
  python3 upload-to-bucket.py              # 전체 브랜드
  python3 upload-to-bucket.py --brand kia  # 특정 브랜드만
  python3 upload-to-bucket.py --dry-run    # 미리보기
  python3 upload-to-bucket.py --force      # 이미 있어도 덮어쓰기
"""

import argparse, json, os, sys
from pathlib import Path
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

BASE = Path(__file__).parent / "_clients"
BRANDS_JSON = BASE / "brands.json"

BUCKET = "vibers-bucket"
ENDPOINT = "https://kr.object.ncloudstorage.com"
PREFIX = "brand-logos"

CDN_BASE = f"https://logo.vibers.co.kr/_clients"  # GitHub Pages CDN (primary)
BUCKET_BASE = f"{ENDPOINT}/{BUCKET}/{PREFIX}"       # 버킷 직접 URL (backup)

CONTENT_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

# 업로드할 파일 패턴 (glob)
UPLOAD_PATTERNS = [
    "logo.svg", "logo.png",
    "logo-800.png", "logo-icon.png",
    "logo-transparent.png", "logo-white.png",
    "logo-alt.svg",
]


def get_s3():
    access_key = os.environ.get("NCP_ACCESS_KEY")
    secret_key = os.environ.get("NCP_SECRET_KEY")
    if not access_key or not secret_key:
        print("❌ NCP_ACCESS_KEY / NCP_SECRET_KEY 환경변수 없음. source ~/.secrets 필요")
        sys.exit(1)
    return boto3.client("s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="kr-standard",
        config=Config(signature_version="s3"),
    )


def upload_brand(s3, brand: dict, dry_run: bool, force: bool) -> dict:
    brand_id = brand["id"]
    brand_dir = BASE / brand_id
    if not brand_dir.exists():
        return {"created": [], "skipped": [], "errors": [f"폴더 없음: {brand_id}"]}

    results = {"created": [], "skipped": [], "errors": []}

    for filename in UPLOAD_PATTERNS:
        file_path = brand_dir / filename
        if not file_path.exists():
            continue

        key = f"{PREFIX}/{brand_id}/{filename}"
        content_type = CONTENT_TYPES.get(file_path.suffix, "application/octet-stream")

        # 이미 존재하는지 확인
        if not force:
            try:
                s3.head_object(Bucket=BUCKET, Key=key)
                results["skipped"].append(filename)
                continue
            except ClientError as e:
                if e.response["Error"]["Code"] != "404":
                    results["errors"].append(f"{filename}: {e}")
                    continue

        if dry_run:
            results["created"].append(f"{filename} [DRY RUN]")
            continue

        try:
            s3.upload_file(
                str(file_path), BUCKET, key,
                ExtraArgs={
                    "ContentType": content_type,
                    "ACL": "public-read",
                    "CacheControl": "public, max-age=86400",
                }
            )
            results["created"].append(filename)
        except Exception as e:
            results["errors"].append(f"{filename}: {e}")

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", help="특정 브랜드 ID만")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="기존 파일도 덮어쓰기")
    args = parser.parse_args()

    s3 = get_s3()
    brands = json.loads(BRANDS_JSON.read_text())["brands"]
    if args.brand:
        brands = [b for b in brands if b["id"] == args.brand]
        if not brands:
            print(f"❌ '{args.brand}' 없음")
            sys.exit(1)

    total = 0
    for brand in brands:
        r = upload_brand(s3, brand, args.dry_run, args.force)
        parts = []
        if r["created"]:
            parts.append(f"✅ {', '.join(r['created'])}")
            total += len(r["created"])
        if r["skipped"]:
            parts.append(f"⏭  {len(r['skipped'])}개 기존")
        if r["errors"]:
            parts.append(f"❌ {', '.join(r['errors'])}")
        print(f"[{brand['name_ko']}] {' | '.join(parts) if parts else '변경 없음'}")

    print(f"\n완료: {total}개 업로드")
    if not args.dry_run:
        print(f"버킷 URL: {ENDPOINT}/{BUCKET}/{PREFIX}/{{brand_id}}/{{file}}")


if __name__ == "__main__":
    main()
