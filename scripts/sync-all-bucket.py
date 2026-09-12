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

# ⚠️ NCP Object Storage 는 boto3 기본 체크섬(aws-chunked 트레일러)을 AccessDenied 로 거절한다.
#    "IP 제한" 으로 오진해 러너 업로드가 몇 주간 실패했다(2026-09-07 확정). 맥은 env
#    AWS_REQUEST_CHECKSUM_CALCULATION=when_required 가 있어 우연히 통과했다.
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
                      request_checksum_calculation="when_required", response_checksum_validation="when_required",
                      retries={"max_attempts": 5, "mode": "standard"}))

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--brand", action="append", default=[], help="선택 브랜드만 동기화 (여러 번 지정 가능)")
    args = ap.parse_args()
    dry = args.dry_run
    s3 = client(); bucket = os.environ["NCP_BUCKET"]
    prefixes = ([f"{PREFIX}{bid}/" for bid in args.brand] +
                [PREFIX+name for name in ("brands.json", "brands-slim.json", "variants-index.json")]) if args.brand else [PREFIX]
    remote = {}
    for prefix in prefixes:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            for o in page.get("Contents", []):
                remote[o["Key"]] = o["Size"]
    todo = []
    if args.brand:
        paths = []
        for bid in args.brand:
            d=BASE/bid
            if d.is_dir(): paths.extend(d.rglob("*"))
        paths.extend(BASE/name for name in ("brands.json", "brands-slim.json", "variants-index.json") if (BASE/name).is_file())
    else:
        paths = BASE.rglob("*")
    for p in paths:
        # _source.json 은 폴더 복구용 내부 메타다. CDN 에 올릴 이유가 없고
        # 4만 개가 버킷을 채운다(2026-09-02 실수로 올림).
        if p.name == "_source.json":
            continue
        if not p.is_file() or p.suffix.lower() not in TYPES:
            continue
        key = PREFIX + str(p.relative_to(BASE))
        # --brand 는 선택 자산과 전역 인덱스만 강제로 올려 크기가 같은 수정도 반영한다.
        sz = p.stat().st_size
        if not args.brand and remote.get(key) == sz:
            # ⚠️ 대상을 **최상위 인덱스 파일로 한정한다.** 브랜드마다 있는
            #    brand.json 까지 내용 비교하면 GET 이 4.5만 번 나가 몇 시간 걸린다
            #    (2026-09-03 에 그렇게 만들었다가 되돌렸다).
            #    크기가 안 변하는 갱신이 실제로 일어나는 건 집계 파일들뿐이다.
            if p.parent != BASE or sz > 65536:
                continue
            try:
                body = s3.get_object(Bucket=bucket, Key=key)['Body'].read()
                if body == p.read_bytes():
                    continue
            except Exception:
                pass                    # 확인 실패하면 올린다 (안전한 쪽)
        todo.append((key, p))
    mb = sum(p.stat().st_size for _, p in todo) / 1024 / 1024
    print(f"로컬 대상 {len(paths):,}개")
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
