#!/usr/bin/env python3
"""
_clients 의 **PNG 외 자산**(SVG·JSON)도 버킷으로 올린다.

왜 —
지금까지 버킷에는 PNG 만 있고 SVG·JSON 은 GitHub Pages 에만 있었다.
그 결과 두 가지 한계에 동시에 부딪혔다.
  · Pages 사이트 1GB 하드 리밋 — SVG 1,078MB 로 이미 초과
  · logo.vibers.co.kr 앞단의 CF 워커가 무료 10만 요청/일 한도에 걸려 429

모든 자산이 버킷에 있으면 워커 없이 storage 경로(NCP nginx → 버킷)로
바로 서빙할 수 있다. 그 경로는 이미 8일째 정상 가동 중이다.

⚠️ ACL: 이 버킷에는 버킷 정책이 없다. 공개는 개별 객체 ACL 로만 된다.
   public-read 를 빼면 CDN 에서 404 가 난다(2026-08-21 실측).

  python3 scripts/sync-all-bucket.py --dry-run
  python3 scripts/sync-all-bucket.py
"""
import os, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"
PREFIX = "_clients/"
# ⚠️ 브랜드 매뉴얼 원본(.ai/.pdf/.zip)도 올린다. 사용자가 내려받을 수 있어야
#    '공식 배포 원본'이라는 값어치가 생긴다. 청년작당소 매뉴얼(4.8MB)이
#    확장자 목록에 없어 CDN 404 였다.
#    .ai 는 실제로 PDF 라 application/pdf 로 내보내야 브라우저가 열어 준다.
TYPES = {".svg": "image/svg+xml", ".json": "application/json", ".jpg": "image/jpeg",
         ".ai": "application/pdf", ".pdf": "application/pdf",
         ".zip": "application/zip", ".eps": "application/postscript"}

def client():
    import boto3
    from botocore.config import Config
    need = ("NCP_ACCESS_KEY", "NCP_SECRET_KEY", "NCP_BUCKET", "NCP_ENDPOINT")
    miss = [n for n in need if not os.environ.get(n)]
    if miss:
        sys.exit(f"환경변수 없음: {', '.join(miss)}")
    return boto3.client("s3", region_name="kr-standard",
        endpoint_url=os.environ["NCP_ENDPOINT"],
        aws_access_key_id=os.environ["NCP_ACCESS_KEY"],
        aws_secret_access_key=os.environ["NCP_SECRET_KEY"],
        config=Config(signature_version="s3v4", max_pool_connections=40,
                      retries={"max_attempts": 5, "mode": "standard"}))

def main():
    dry = "--dry-run" in sys.argv
    s3 = client(); bucket = os.environ["NCP_BUCKET"]
    remote = {}
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PREFIX):
        for o in page.get("Contents", []):
            remote[o["Key"]] = o["Size"]
    todo = []
    for p in BASE.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TYPES:
            continue
        key = PREFIX + str(p.relative_to(BASE))
        if remote.get(key) == p.stat().st_size:
            continue                    # 같은 크기면 건너뛴다(멱등)
        todo.append((key, p))
    mb = sum(p.stat().st_size for _, p in todo) / 1024 / 1024
    print(f"로컬 대상 {sum(1 for p in BASE.rglob('*') if p.is_file() and p.suffix.lower() in TYPES):,}개")
    print(f"버킷 보유 {len(remote):,}개 → 올릴 것 {len(todo):,}개 ({mb:.0f}MB)")
    if dry or not todo:
        return 0
    n = 0; fail = []; lock = threading.Lock()
    def put(item):
        nonlocal n
        key, path = item
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=path.read_bytes(),
                          ACL="public-read",            # ⚠️ 빼면 CDN 404
                          ContentType=TYPES[path.suffix.lower()],
                          CacheControl="public, max-age=31536000, immutable")
        except Exception as e:
            with lock: fail.append(f"{key}: {e}")
        with lock:
            n += 1
            if n % 2000 == 0: print(f"  {n:,}/{len(todo):,}", flush=True)
    with ThreadPoolExecutor(max_workers=24) as ex:
        list(ex.map(put, todo))
    print(f"✅ 업로드 {n - len(fail):,}개" + (f" | ❌ 실패 {len(fail):,}" if fail else ""))
    for f in fail[:5]: print("   ", f[:120])
    return 1 if fail else 0

sys.exit(main())
