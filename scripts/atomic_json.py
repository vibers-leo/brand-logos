#!/usr/bin/env python3
"""JSON 을 원자적으로 쓴다 — 동시 쓰기로 파일이 깨지지 않게.

2026-09-02 에 brands.json 이 두 번 깨졌다. 파생물 생성과 수집기가 같은
파일에 동시에 쓰면서 한쪽의 write() 가 다른 쪽 내용을 반쯤 덮었다.
9.8MB 를 통째로 쓰는 데 시간이 걸려 겹칠 확률이 높다.

같은 디렉토리에 임시 파일로 쓴 뒤 os.replace 로 갈아 끼운다.
replace 는 같은 볼륨 안에서 원자적이라 **반쯤 쓰인 파일이 보이지 않는다.**
"""
import json, os, tempfile
from pathlib import Path


def write_json(path, data, *, indent=None, separators=(",", ":")):
    if separators is None:
        separators = None   # indent 를 쓸 때는 기본 구분자를 그대로 둔다
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent, separators=separators)
            f.flush()
            os.fsync(f.fileno())
        # 쓰기 전에 한 번 읽어 검증한다 — 깨진 것을 넘기지 않는다
        with open(tmp) as f:
            json.load(f)
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise


# ── 잃어버린 갱신(lost update) 막기 ────────────────────────────────
# ⚠️ **원자적 쓰기는 파손만 막는다. 덮어쓰기는 못 막는다.**
# 수집기 셋이 동시에 돌면 각자 read → merge → write 를 하는데,
# 셋 다 원자적으로 써도 **마지막 하나만 남고 나머지 추가분은 사라진다.**
# 파일은 멀쩡하니 에러도 안 난다 — 폴더만 남고 레코드가 없어진다.
# 2026-09-02 에 이렇게 148건이 사라졌다 (앞서 파손으로 잃은 357건과 별개).
#
# 고치는 법은 원자성이 아니라 **상호배제**다. 읽기 직전에 락을 잡고
# 쓰기가 끝난 뒤에 놓는다. 그 사이 다른 프로세스는 기다린다.
import fcntl
from contextlib import contextmanager


@contextmanager
def locked(path, timeout=300):
    """`path` 에 대한 배타 락. read-modify-write 전체를 이걸로 감싼다.

        with atomic_json.locked(p):
            data = json.loads(p.read_text())
            data.append(...)
            atomic_json.write_json(p, data)

    락 파일은 `{path}.lock` 으로 따로 둔다 — 대상 파일 자체를 잠그면
    os.replace 로 inode 가 갈리면서 락이 딴 파일에 남는다.
    """
    lock = Path(str(path) + ".lock")
    f = open(lock, "w")
    try:
        import time
        t0 = time.time()
        while True:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() - t0 > timeout:
                    raise TimeoutError(f"{lock} 락 대기 {timeout}s 초과")
                time.sleep(0.2)
        yield
    finally:
        try: fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError: pass
        f.close()
