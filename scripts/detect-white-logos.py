#!/usr/bin/env python3
"""흰 배경에서 안 보이는 로고를 찾아 `light_bg_unsafe` 를 붙인다.

⚠️ 기존 `dark_variant` 와 다른 값이다. 그건 "다크 배경에서 투명본과 화이트본 중
무엇을 쓸까"라서 45,283건 중 44,115건(97%)에 붙어 있고 판정에 못 쓴다.
판정은 **두 경우를 갈라야** 한다. 흰 비율만 재면 35%가 걸리는데 대부분 오탐이다:

  ① 배경이 구워진 PNG  — 불투명 픽셀에 흰 배경까지 포함돼 흰 비율이 90%를 넘는다.
     Raytheon(빨간 글씨)이 91%로 나왔다. 이건 흰 배경 위에서 멀쩡히 보인다.
  ② 투명 배경의 흰 잉크 — 이것만 진짜 안 보인다.

가르는 값은 **불투명 비율**이다. 이미지 전체가 불투명하면(>92%) 배경이 구워진 것이다.
실측(1,493 표본): 배경구움 1,378 · 투명+유색 98 · 투명+흰잉크 **17 (1.1%)**.
"""
import json, sys, argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from PIL import Image
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import atomic_json

C = Path(__file__).resolve().parent.parent / "_clients"
NEAR_WHITE  = 225     # 이 이상이면 흰색으로 친다
WHITE_RATIO = 0.88    # 투명 배경에서 잉크의 이만큼이 흰색이면 안 보인다
OPAQUE_MAX  = 0.92    # 이보다 불투명하면 배경이 구워진 것 — 판정 대상 아님


def measure(bid: str):
    for fn in ("logo-800.png", "logo.png"):
        p = C / bid / fn
        if p.exists():
            break
    else:
        return bid, None
    try:
        im = Image.open(p).convert("RGBA")
        im.thumbnail((160, 160))
        a = np.array(im)
    except Exception:
        return bid, None
    al = a[..., 3]
    op = al > 40
    n = int(op.sum())
    if n < 40:
        return bid, None
    if n / al.size > OPAQUE_MAX:
        return bid, 0.0            # 배경 구움 — 흰 배경에서 안전
    rgb = a[..., :3][op].astype(int)
    white = ((rgb > NEAR_WHITE).all(axis=1)).sum()
    return bid, round(float(white) / n, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    raw = json.loads((C / "brands.json").read_text())
    br = raw["brands"] if isinstance(raw, dict) else raw
    ids = [b["id"] for b in br][: a.limit] if a.limit else [b["id"] for b in br]

    res = {}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (bid, r) in enumerate(ex.map(measure, ids, chunksize=64), 1):
            if r is not None:
                res[bid] = r
            if i % 5000 == 0:
                print(f"  {i:,}/{len(ids):,}", flush=True)

    unsafe = {k for k, v in res.items() if v >= WHITE_RATIO}
    print(f"\n측정 {len(res):,} · 흰 배경 위험 {len(unsafe):,} ({len(unsafe)/max(1,len(res))*100:.1f}%)")
    for th in (0.95, 0.9, 0.88, 0.8):
        print(f"    흰비율 ≥{th:.0%}  {sum(1 for v in res.values() if v>=th):,}")
    if a.dry_run:
        print("  (--dry-run — 저장 안 함)")
        for k in list(unsafe)[:10]:
            print(f"    {k}  {res[k]:.0%}")
        return

    with atomic_json.locked(C / "brands.json"):
        raw = json.loads((C / "brands.json").read_text())
        br = raw["brands"] if isinstance(raw, dict) else raw
        n = 0
        for b in br:
            v = res.get(b["id"])
            if v is None:
                continue
            want = v >= WHITE_RATIO
            if want != bool(b.get("light_bg_unsafe")):
                if want:
                    b["light_bg_unsafe"] = True
                else:
                    b.pop("light_bg_unsafe", None)
                n += 1
        if isinstance(raw, dict):
            raw["brands"] = br
        atomic_json.write_json(C / "brands.json", raw if isinstance(raw, dict) else br)
        print(f"  ✅ {n:,}건 갱신")


if __name__ == "__main__":
    main()
