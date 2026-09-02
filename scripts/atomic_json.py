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
