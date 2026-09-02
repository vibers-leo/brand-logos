#!/usr/bin/env python3
"""PNG 로만 서비스 중인 브랜드의 홈페이지에서 **벡터를 찾아 채워 넣는다.**

신규 수집과 흐름이 다르다 — 새 폴더를 만드는 게 아니라 **이미 있는 폴더에
logo.svg 를 넣고** has_svg 를 올린다. 그래서 id 를 새로 만들지 않는다.

SVG 가 아닌 후보는 전부 버린다. 이미 PNG 는 갖고 있으므로 PNG 를 또 받아봐야
바뀌는 게 없다. 오히려 멀쩡한 PNG 를 덜 좋은 것으로 갈아치울 위험만 있다.

  python3 scripts/upgrade-to-svg.py --limit 300 [--dry-run]
"""
import sys, json, asyncio, argparse, hashlib
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
C = BASE / "_clients"
sys.path.insert(0, str(BASE / "scripts"))

# ⚠️ collect-krx-rendered 는 **모듈 로드 시점에 sys.argv 를 읽는다**(SOURCES 선택).
#    import 전에 argv 를 안전한 값으로 바꿔놓지 않으면 우리 인자를 보고 죽는다.
_argv = sys.argv[:]
sys.argv = [sys.argv[0]]
import importlib.util as _il
_spec = _il.spec_from_file_location("ckr", BASE / "scripts" / "collect-krx-rendered.py")
ckr = _il.module_from_spec(_spec); _spec.loader.exec_module(ckr)
sys.argv = _argv

import atomic_json


def targets(limit):
    raw = json.loads((C / "brands.json").read_text())
    br = raw["brands"] if isinstance(raw, dict) else raw
    byid = {b["id"]: b for b in br}
    want = json.loads((C / "svg-wanted.json").read_text())
    out = []
    for w in want:
        b = byid.get(w["id"])
        if not b or b.get("has_svg") or b.get("hidden"):
            continue
        site = b.get("website") or (f"https://{b['domain']}" if b.get("domain") else None)
        if not site:
            continue
        out.append({"id": b["id"], "name": b.get("name_ko") or b.get("name_en"), "site": site})
        if limit and len(out) >= limit:
            break
    return out


async def run(a):
    todo = targets(a.limit)
    print(f"대상 {len(todo)}건 (PNG 로 서비스 중 · 홈페이지 있음)\n")
    exe = ckr._find_browser()
    if not exe:
        print("❌ 브라우저 없음"); return
    from playwright.async_api import async_playwright
    hit = miss = 0
    upgraded = []
    seen = set()
    async with async_playwright() as p:
        br_ = await p.chromium.launch(executable_path=exe, headless=True)
        pg = await br_.new_page()
        for x in todo:
            got, why = await ckr.probe(pg, x["site"])
            if not got:
                print(f"   {x['name'][:14]:<16} 접속❌ {why[:40]}"); miss += 1; continue
            chosen = None; reasons = []
            for top in got[:6]:
                data, ext = ckr.fetch_candidate(top, x["site"])
                if data is None:
                    reasons.append(f"{top['why']}:{ext}"); continue
                if ext != "svg":
                    reasons.append(f"{top['why']}:svg아님({ext})"); continue
                ok_, note = ckr.accept(data, True)
                if ok_:
                    chosen = (top, data, note); break
                reasons.append(f"{top['why']}:{note}")
            if not chosen:
                print(f"   {x['name'][:14]:<16} — {' | '.join(reasons[:3])}"); miss += 1; continue
            top, data, note = chosen
            sig = hashlib.sha1(data).hexdigest()[:16]
            if sig in seen:
                print(f"   {x['name'][:14]:<16} — 같은 SVG 중복"); miss += 1; continue
            seen.add(sig)
            print(f"   {x['name'][:14]:<16} ✅ SVG [{top['why']}] {note}")
            hit += 1
            if not a.dry_run:
                (C / x["id"] / "logo.svg").write_bytes(data)
                upgraded.append(x["id"])
        await br_.close()
    print(f"\n  벡터 확보 {hit} · 실패 {miss}  ({hit/max(1,hit+miss)*100:.0f}%)")
    if not upgraded:
        return
    with atomic_json.locked(C / "brands.json"):
        raw = json.loads((C / "brands.json").read_text())
        br = raw["brands"] if isinstance(raw, dict) else raw
        up = set(upgraded); n = 0
        for b in br:
            if b["id"] in up:
                b["has_svg"] = True; b["logo_svg"] = "logo.svg"; n += 1
        if isinstance(raw, dict): raw["brands"] = br
        atomic_json.write_json(C / "brands.json", raw if isinstance(raw, dict) else br)
    print(f"  ✅ {n}건 SVG 승격")
    print(f"  다음: python3 build-variants.py --force  (PNG 파생물을 새 SVG 로 다시 만든다)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true")
    asyncio.run(run(ap.parse_args()))
