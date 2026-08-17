#!/usr/bin/env python3
"""
_clients 아래 PNG 를 NCP 오브젝트 스토리지로 동기화한다.

왜 —
GitHub Pages 는 사이트 용량 1GB 가 하드 리밋인데 PNG 파생물이 전체의 79%를
먹고 있었다. 원본 SVG 는 70MB 뿐이고 PNG 는 전부 SVG 에서 재생성 가능하다.
PNG 를 버킷으로 내보내면 브랜드를 5만 개까지 늘려도 Pages 가 버틴다.
서빙은 logo-guard 워커가 한다 (버킷에 없으면 Pages 로 폴백).

멱등하다 — 같은 크기의 객체가 이미 있으면 건너뛴다. 매일 돌려도 된다.

  python3 scripts/sync-png-bucket.py            # 올릴 것만 올린다
  python3 scripts/sync-png-bucket.py --dry-run  # 무엇이 올라갈지만 본다
  python3 scripts/sync-png-bucket.py --verify   # 업로드분 표본 대조
"""
import argparse
import os
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"
PREFIX = "_clients/"


def client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        sys.exit("boto3 가 없다: pip install boto3")
    need = ("NCP_ACCESS_KEY", "NCP_SECRET_KEY", "NCP_BUCKET", "NCP_ENDPOINT")
    miss = [n for n in need if not os.environ.get(n)]
    if miss:
        # 조용히 넘어가면 '올릴 게 없다'로 보여서 이관이 안 된 걸 모른다
        sys.exit(f"환경변수 없음: {', '.join(miss)} — .secrets/보안.env 를 source 한다")
    return boto3.client(
        "s3",
        region_name="kr-standard",
        endpoint_url=os.environ["NCP_ENDPOINT"],
        aws_access_key_id=os.environ["NCP_ACCESS_KEY"],
        aws_secret_access_key=os.environ["NCP_SECRET_KEY"],
        # 스레드로 병렬 업로드하므로 커넥션 풀을 넉넉히 잡는다
        config=Config(signature_version="s3v4", max_pool_connections=40,
                      retries={"max_attempts": 5, "mode": "standard"}),
    )


def remote_sizes(s3, bucket: str) -> dict[str, int]:
    """버킷에 이미 있는 객체의 크기. 한 번에 받아 두고 대조에 쓴다."""
    sizes: dict[str, int] = {}
    tok = None
    while True:
        kw = {"Bucket": bucket, "Prefix": PREFIX, "MaxKeys": 1000}
        if tok:
            kw["ContinuationToken"] = tok
        r = s3.list_objects_v2(**kw)
        for o in r.get("Contents", []):
            sizes[o["Key"]] = o["Size"]
        if not r.get("IsTruncated"):
            return sizes
        tok = r["NextContinuationToken"]


def local_pngs() -> list[tuple[str, Path, int]]:
    out = []
    for d in sorted(os.scandir(BASE), key=lambda e: e.name):
        if not d.is_dir():
            continue
        for root, _, files in os.walk(d.path):
            for f in files:
                if not f.lower().endswith(".png"):
                    continue
                p = Path(root) / f
                out.append((PREFIX + str(p.relative_to(BASE)), p, p.stat().st_size))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", type=int, default=0, help="표본 N개를 CDN 으로 대조")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    s3 = client()
    bucket = os.environ["NCP_BUCKET"]

    files = local_pngs()
    total = sum(s for _, _, s in files)
    print(f"로컬 PNG {len(files):,}개 / {total/1024/1024:.0f}MB")

    have = remote_sizes(s3, bucket)
    todo = [(k, p, s) for k, p, s in files if have.get(k) != s]
    print(f"버킷 보유 {len(have):,}개 → 올릴 것 {len(todo):,}개 "
          f"({sum(s for _,_,s in todo)/1024/1024:.0f}MB)")

    if args.dry_run:
        return 0
    if not todo:
        # 올릴 게 없어도 --verify 는 돌아야 한다. 이관이 이미 끝난 뒤에
        # "정말 CDN 으로 나오는가"를 확인할 수단이 있어야 파일을 지울 수 있다.
        print("✅ 이미 최신")

    done = threading.Semaphore(0)
    fail: list[str] = []
    lock = threading.Lock()
    n = 0

    def put(item):
        nonlocal n
        key, path, _ = item
        try:
            s3.put_object(
                Bucket=bucket, Key=key, Body=path.read_bytes(),
                ContentType="image/png", ACL="public-read",
                CacheControl="public, max-age=31536000, immutable",
            )
        except Exception as e:
            with lock:
                fail.append(f"{key}: {e}")
        with lock:
            n += 1
            if n % 500 == 0:
                print(f"  {n:,}/{len(todo):,}", flush=True)

    if todo:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(put, todo))

    if fail:
        # 실패를 빈 결과로 흡수하지 않는다 — 몇 개가 왜 실패했는지 남긴다
        print(f"❌ 업로드 실패 {len(fail)}개")
        for f in fail[:10]:
            print("   " + f)
        return 1

    if todo:
        print(f"✅ 업로드 {len(todo):,}개 완료")

    if args.verify:
        import urllib.request
        sample = random.sample(files, min(args.verify, len(files)))
        bad = 0
        for key, path, _ in sample:
            url = f"https://logo.vibers.co.kr/{key}"
            # User-Agent 를 안 주면 Cloudflare 봇 필터가 403 을 준다.
            # 그걸 '업로드 실패'로 읽으면 멀쩡한 이관을 되돌리게 된다(실제로 겪음).
            req = urllib.request.Request(url, headers={
                "Referer": "https://semologo.com/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
            })
            try:
                got = urllib.request.urlopen(req, timeout=30).read()
            except Exception as e:
                print(f"   {key}: {e}")
                bad += 1
                continue
            if got != path.read_bytes():
                print(f"   {key}: 바이트 불일치 (로컬 {path.stat().st_size} / CDN {len(got)})")
                bad += 1
        print(f"{'❌' if bad else '✅'} 표본 대조 {len(sample)}개 중 불일치 {bad}개")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
