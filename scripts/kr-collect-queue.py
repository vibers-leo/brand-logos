#!/usr/bin/env python3
"""국내 수집 대상 큐 — 크론이 매주 여기서 할 일을 꺼내 쓴다.

■ 왜 큐가 필요한가
국내 수집기(collect-krx·collect-kr-institutions·collect-kr-pass2)는 **일회성
전수조사**다. 명단이 고정돼 있어서 한 번 훑으면 다음날 새로 생기는 게 거의 없다.
실측: 신규 상장이 연평균 106건 = **하루 0.29건**. 지자체·대학은 더 느리다.

그래서 크론의 값어치는 수확량이 아니라 **누락 방지**에 있다:
  ① 접속 실패했던 곳을 계속 재시도한다 (일시적 장애가 많다 — 실측 site_fail 529건)
  ② 새로 상장·개원·개교한 곳을 놓치지 않는다
  ③ **기관이 CI 를 바꿨는지 확인한다** ← 장기적으로 가장 값지다
     카탈로그 4만 개인데 낡은 로고를 들고 있으면 신뢰가 깨진다.
     로고 교체는 신규 상장보다 잦다.

큐는 상태를 들고 있어서 매번 3,500곳을 다시 훑지 않는다.

  python3 scripts/kr-collect-queue.py --build     # 큐 생성·갱신
  python3 scripts/kr-collect-queue.py --stats     # 현황
  python3 scripts/kr-collect-queue.py --due 300   # 이번 회차에 볼 대상 출력
"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
QUEUE = ROOT / "_kr-queue.json"

# 재시도 간격(일). 실패가 쌓일수록 뜸하게 본다 — 죽은 사이트를 매주 두드리지 않는다.
BACKOFF = [1, 3, 7, 14, 30, 90]
# 이미 확보한 브랜드의 로고 변경 확인 주기(일)
RECHECK_DAYS = 90


def today():
    return time.strftime("%Y-%m-%d")


def days_since(d):
    if not d:
        return 9999
    try:
        return int((time.time() - time.mktime(time.strptime(d, "%Y-%m-%d"))) / 86400)
    except Exception:
        return 9999


def build():
    q = json.loads(QUEUE.read_text()) if QUEUE.exists() else {}
    bl = json.loads((C / "brands.json").read_text())
    bl = bl["brands"] if isinstance(bl, dict) else bl

    norm = lambda s: re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())
    have = {}
    for b in bl:
        d = str(b.get("domain") or "").lower().replace("www.", "")
        if d:
            have[d] = b["id"]

    added = 0
    # 명단 원본들 — 수집기가 쓰는 것과 같은 파일이다
    srcs = [(str(ROOT / "_targets" / "krx.json"), "krx", lambda r: (r["name"], r.get("site", ""))),
            (str(ROOT / "_targets" / "sgg-targets.json"), "muni", lambda r: (r["name"], r.get("site", "")))]
    for path, kind, pick in srcs:
        p = Path(path)
        if not p.exists():
            continue
        for r in json.loads(p.read_text()):
            name, site = pick(r)
            if not site:
                continue
            d = re.sub(r"^https?://(www\.)?|/.*$", "", site).lower()
            key = d or norm(name)
            if key in q:
                continue
            q[key] = {"name": name, "site": site, "kind": kind,
                      "state": "have" if d in have else "todo",
                      "brand_id": have.get(d), "fails": 0,
                      "last_try": None, "last_ok": today() if d in have else None}
            added += 1

    # 이미 카탈로그에 있는데 큐에 상태가 안 붙은 것들을 맞춘다
    synced = 0
    for k, v in q.items():
        d = re.sub(r"^https?://(www\.)?|/.*$", "", v.get("site") or "").lower()
        if d in have and v["state"] != "have":
            v.update(state="have", brand_id=have[d], fails=0, last_ok=today())
            synced += 1

    QUEUE.write_text(json.dumps(q, ensure_ascii=False, separators=(",", ":")))
    print(f"큐 {len(q):,}건 (신규 {added} · 상태동기 {synced})")
    return 0


def stats():
    if not QUEUE.exists():
        print("큐 없음 — --build 먼저")
        return 1
    q = json.loads(QUEUE.read_text())
    from collections import Counter
    st = Counter(v["state"] for v in q.values())
    kd = Counter(v["kind"] for v in q.values())
    print(f"큐 {len(q):,}건")
    print("  상태: " + " · ".join(f"{k} {v:,}" for k, v in st.most_common()))
    print("  분류: " + " · ".join(f"{k} {v:,}" for k, v in kd.most_common()))
    due = [v for v in q.values() if is_due(v)]
    print(f"  이번 회차 대상: {len(due):,}건")
    return 0


def is_due(v):
    """이 항목을 지금 봐야 하나."""
    if v["state"] == "have":
        # 확보한 것도 주기적으로 로고가 바뀌었는지 본다
        return days_since(v.get("last_ok")) >= RECHECK_DAYS
    wait = BACKOFF[min(v.get("fails", 0), len(BACKOFF) - 1)]
    return days_since(v.get("last_try")) >= wait


def due(n):
    q = json.loads(QUEUE.read_text())
    rows = [dict(v, key=k) for k, v in q.items() if is_due(v)]
    # 아직 못 구한 것을 먼저, 그다음 재확인 대상
    rows.sort(key=lambda v: (v["state"] == "have", v.get("fails", 0)))
    out = rows[:n]
    print(json.dumps(out, ensure_ascii=False))
    return 0


def main():
    if "--build" in sys.argv:
        return build()
    if "--stats" in sys.argv:
        return stats()
    if "--due" in sys.argv:
        i = sys.argv.index("--due")
        return due(int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 200)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
