#!/usr/bin/env python3
"""
누락된 로고 '형태'를 targeted 로 수집한다.

기존 수집기는 소스 카탈로그를 훑는 방식(source-first)이라, 이미 있는 브랜드에
**빠진 형태**를 채우는 일은 못 했다. 이 스크립트는 반대로 brand-first 로 간다:

  심볼만 있는 브랜드   → 텍스트가 있는 풀버전을 찾아 온다
  텍스트만 있는 브랜드 → 심볼 버전을 찾아 온다

소스는 Iconify `logos` 컬렉션. 같은 브랜드의 형태 변형이 슬러그 규칙으로
정리돼 있어서(`{name}` 풀버전 / `{name}-icon` 심볼) 매칭이 확실하다.
JSON 한 번만 받으면 아이콘별 네트워크 요청이 필요 없다.

받은 파일은 `sources/iconify/*.svg` 로 **추가만** 한다. 기존 logo.svg 는
절대 건드리지 않는다 (대표 교체는 사람이 투표로 정하는 별도 흐름이다).

사용:
  python3 scripts/collect-missing-forms.py --dry-run
  python3 scripts/collect-missing-forms.py --limit 50
  python3 scripts/collect-missing-forms.py
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "_clients"
BRANDS_JSON = BASE / "brands.json"
ICONIFY_URL = "https://raw.githubusercontent.com/iconify/icon-sets/master/json/logos.json"
CACHE = Path("/tmp/iconify-logos.json")
UA = {"User-Agent": "Mozilla/5.0 (compatible; vibers-logo-collector)"}


def load_iconify() -> dict:
    if CACHE.exists() and CACHE.stat().st_size > 1_000_000:
        return json.loads(CACHE.read_text())
    req = urllib.request.Request(ICONIFY_URL, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read()
    CACHE.write_bytes(data)
    return json.loads(data)


def build_svg(coll: dict, name: str) -> str | None:
    """Iconify 아이콘 정의 → 독립 SVG 문자열."""
    ic = coll.get("icons", {}).get(name)
    if not ic or not ic.get("body"):
        return None
    w = ic.get("width", coll.get("width", 24))
    h = ic.get("height", coll.get("height", 24))
    left = ic.get("left", coll.get("left", 0))
    top = ic.get("top", coll.get("top", 0))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{left} {top} {w} {h}">{ic["body"]}</svg>')


def current_forms(brand_dir: Path) -> set[str]:
    """이 브랜드가 지금 갖고 있는 형태 (매니페스트 기준)."""
    mp = brand_dir / "variants.json"
    if not mp.exists():
        return set()
    try:
        return {v["form"] for v in json.loads(mp.read_text()).get("variants", [])}
    except Exception:
        return set()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    coll = load_iconify()
    icons = set(coll.get("icons", {}).keys())
    print(f"Iconify logos 아이콘 {len(icons):,}개")

    data = json.loads(BRANDS_JSON.read_text())
    brands = data["brands"]

    all_ids = {b["id"] for b in brands}

    plans: list[tuple[str, str, str]] = []      # (brand_id, iconify_name, 무엇을 채우나)
    for b in brands:
        bid = b["id"]
        d = BASE / bid
        if not d.is_dir():
            continue
        forms = current_forms(d)
        if not forms or len(forms) > 1:
            continue                            # 이미 여러 형태가 있으면 대상 아님

        # `X-icon` 인데 부모 `X` 가 코퍼스에 있으면 통합 대상이다.
        # 통합되면 이 항목 자체가 사라지므로 여기에 수집해봐야 버려진다.
        if bid.endswith("-icon") and bid[:-5] in all_ids:
            continue

        only = next(iter(forms))
        if only == "symbol":
            # 심볼만 있다 → 텍스트가 든 풀버전을 찾는다
            base = bid[:-5] if bid.endswith("-icon") else bid
            cand = base if (base != bid and base in icons) else f"{bid}-wordmark"
            if cand in icons:
                plans.append((bid, cand, "텍스트판"))
        else:
            # 텍스트만 있다 → 심볼을 찾는다
            cand = f"{bid}-icon"
            if cand in icons:
                plans.append((bid, cand, "심볼"))

    if args.limit:
        plans = plans[: args.limit]
    print(f"수집 대상 {len(plans)}건 "
          f"(텍스트판 {sum(1 for p in plans if p[2]=='텍스트판')} / "
          f"심볼 {sum(1 for p in plans if p[2]=='심볼')})")

    if args.dry_run:
        for bid, name, what in plans[:25]:
            print(f"  {bid:28} ← iconify:{name:28} ({what})")
        return 0

    by_id = {b["id"]: b for b in brands}
    added = skipped = failed = registered = 0
    for bid, name, what in plans:
        d = BASE / bid
        rel = f"sources/iconify/{name}.svg"
        out = d / rel
        if out.exists():
            # 파일은 있는데 sources[] 에 등록이 안 된 경우가 있다.
            # 매니페스트 생성기는 sources[] 만 보므로, 등록이 없으면 파일이
            # 있어도 변형으로 잡히지 않는다 — 여기서 반드시 채워준다.
            skipped += 1
        else:
            svg = build_svg(coll, name)
            if not svg or "<" not in svg:
                failed += 1
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(svg)
            added += 1

        # sources[] 등록은 파일 존재 여부와 무관하게 항상 확인한다
        e = by_id[bid]
        srcs = e.setdefault("sources", [])
        if not any(s.get("file") == rel for s in srcs):
            srcs.append({"provider": f"iconify:{name}", "file": rel,
                         "label": "아이콘형" if what == "심볼" else "워드마크형"})
            registered += 1
        if added % 50 == 0:
            print(f"  ... {added}건 추가", flush=True)

    if added or registered:
        BRANDS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\n파일 추가 {added} | 기존 파일 {skipped} | sources 등록 {registered} | 실패 {failed}")
    print("→ 이어서 실행: scripts/build-logo-variants.py && scripts/build-slim.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
