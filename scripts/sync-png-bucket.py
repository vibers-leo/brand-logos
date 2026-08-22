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
  python3 scripts/sync-png-bucket.py --pull     # 버킷 → 로컬 (없는 것만)

⚠️ --pull 은 CI 에서 **build-variants 앞에** 반드시 돌려야 한다.
저장소에 PNG 가 없으므로, 안 받아 오면 build-variants 가 "없으니 만들자"로
판단해 매 실행마다 3만 개를 다시 만든다. 결과물은 같지만 몇십 분을 버린다.
로컬에서도 마찬가지다 — rebase 로 워킹트리가 정리되면 PNG 가 사라진다.
"""
import argparse
import os
import random
import re
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
    # GitHub Secrets를 웹 UI에서 등록하면 끝 개행이 섞일 수 있다. endpoint URL은
    # 개행 하나로 boto3 초기화가 즉시 실패하므로, 경계에서 한 번만 정규화한다.
    env = {name: os.environ.get(name, "").strip() for name in need}
    endpoint = env["NCP_ENDPOINT"].strip("'\"")
    # Secret을 `.env` 줄 전체(`NCP_ENDPOINT=https://…`)로 붙여 넣은 경우와
    # 호스트만 넣은 경우를 모두 받아 준다. 실제 값은 로그에 절대 찍지 않는다.
    # 일부 시크릿 관리 도구는 `.env` 파일 조각을 통째로 저장한다. endpoint 행만
    # 고른다. 행이 하나뿐인 정상 값도 그대로 유지된다.
    endpoint_lines = [line.strip() for line in endpoint.splitlines() if line.strip()]
    endpoint = next((re.sub(r"^(?:export\\s+)?NCP_ENDPOINT\\s*=\\s*", "", line, flags=re.I)
                     for line in endpoint_lines
                     if re.match(r"^(?:export\\s+)?NCP_ENDPOINT\\s*=", line, flags=re.I)),
                    endpoint_lines[0] if endpoint_lines else "")
    endpoint = endpoint.strip("'\"")
    if endpoint and not re.match(r"^https?://", endpoint, flags=re.I):
        endpoint = "https://" + endpoint
    env["NCP_ENDPOINT"] = endpoint.rstrip("/")
    miss = [name for name, value in env.items() if not value]
    if miss:
        # 조용히 넘어가면 '올릴 게 없다'로 보여서 이관이 안 된 걸 모른다
        sys.exit(f"환경변수 없음: {', '.join(miss)} — .secrets/보안.env 를 source 한다")
    return boto3.client(
        "s3",
        region_name="kr-standard",
        endpoint_url=env["NCP_ENDPOINT"],
        aws_access_key_id=env["NCP_ACCESS_KEY"],
        aws_secret_access_key=env["NCP_SECRET_KEY"],
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
    ap.add_argument("--pull", action="store_true",
                    help="버킷에 있고 로컬에 없는 PNG 를 내려받는다 (CI 필수)")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    s3 = client()
    bucket = os.environ["NCP_BUCKET"].strip()

    files = local_pngs()
    total = sum(s for _, _, s in files)
    print(f"로컬 PNG {len(files):,}개 / {total/1024/1024:.0f}MB")

    have = remote_sizes(s3, bucket)

    if args.pull:
        local = {k for k, _, _ in files}
        want = [(k, sz) for k, sz in have.items() if k not in local]
        print(f"내려받을 것 {len(want):,}개 ({sum(sz for _, sz in want)/1024/1024:.0f}MB)")
        if not want:
            print("✅ 로컬이 이미 최신")
            return 0
        lock2 = threading.Lock()
        got = [0]
        bad2: list[str] = []

        def pull_one(item):
            key, _ = item
            dest = BASE / key[len(PREFIX):]
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                dest.write_bytes(body)
            except Exception as e:
                with lock2:
                    bad2.append(f"{key}: {e}")
                return
            with lock2:
                got[0] += 1
                if got[0] % 2000 == 0:
                    print(f"  {got[0]:,}/{len(want):,}", flush=True)

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(pull_one, want))
        if bad2:
            print(f"❌ 내려받기 실패 {len(bad2)}개")
            for b in bad2[:10]:
                print("   " + b)
            return 1
        print(f"✅ 내려받기 {got[0]:,}개 완료")
        return 0
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
