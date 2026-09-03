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
WHITE_RATIO = 0.60    # 투명 배경에서 잉크의 이만큼이 흰색이면 검정 배경으로 보낸다
# 2026-09-04 눈검사: 60~88% 구간은 '색 심볼 + 흰 글자'(kict·JYP·FC서울·대성·WMTV…)라
# 흰 배경에서 글자가 사라진다. 흰 채움 아이콘(chai·blocs·kookmin)도 검정에서 멀쩡하다.
# 45~60% 는 반반(흰 글자형 vs 흰 채움 아이콘형)이라 자동으로 못 가른다 → bg-overrides 로.
OVERRIDES = C / "bg-overrides.json"   # {id: "dark"|"light"} — 사이트 모달에서 손으로 찍은 것. 자동 판정보다 우선.
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

    overrides = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    if overrides:
        print(f"  수동 지정 {len(overrides)}건 반영 (bg-overrides.json)")
    with atomic_json.locked(C / "brands.json"):
        raw = json.loads((C / "brands.json").read_text())
        br = raw["brands"] if isinstance(raw, dict) else raw
        n = 0
        for b in br:
            v = res.get(b["id"])
            if v is None:
                continue
            # 필드는 `light_logo` 하나로 통일한다 — slim 의 `light` 와
            # 프론트의 검정 카드(#18181b)가 이미 이 값을 본다.
            # 별도 필드를 두면 프론트가 못 읽어 아무 효과가 없다.
            want = v >= WHITE_RATIO
            ov = overrides.get(b["id"])
            if ov == "dark": want = True
            elif ov == "light": want = False
            if want != bool(b.get("light_logo")):
                if want:
                    b["light_logo"] = True
                else:
                    b.pop("light_logo", None)
                n += 1
            b.pop("light_bg_unsafe", None)
        if isinstance(raw, dict):
            raw["brands"] = br
        atomic_json.write_json(C / "brands.json", raw if isinstance(raw, dict) else br)
        print(f"  ✅ {n:,}건 갱신")


if __name__ == "__main__":
    main()
