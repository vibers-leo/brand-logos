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
REVIEW = C / "_svg-review"      # 모양 불일치 후보. 커밋하지 않는다(.gitignore)
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


def _same_shape(png_path, svg_bytes, N=32):
    """기존 PNG 와 새 SVG 렌더의 종횡비·정규화 실루엣을 비교한다. (참, 사유)"""
    import io, numpy as np
    from PIL import Image
    import safesvg, cairosvg
    try:
        a = Image.open(png_path).convert("RGBA")
        b = Image.open(io.BytesIO(cairosvg.svg2png(
            bytestring=safesvg.sanitize(safesvg.inline_internal_entities(svg_bytes)),
            output_width=400))).convert("RGBA")
    except Exception as e:
        return False, f"렌더실패 {type(e).__name__}"
    def sil(im):
        al = np.array(im)[..., 3] > 40
        ys, xs = np.where(al)
        if len(xs) < 20: return None, None
        crop = al[ys.min():ys.max()+1, xs.min():xs.max()+1]
        ar = crop.shape[1] / crop.shape[0]
        t = np.array(Image.fromarray((crop*255).astype("uint8")).resize((N, N), Image.LANCZOS), float)/255
        return ar, t
    ar1, t1 = sil(a); ar2, t2 = sil(b)
    if t1 is None or t2 is None: return False, "빈 이미지"
    if abs(ar1-ar2)/max(ar1, ar2) > 0.35:
        return False, f"종횡비 {ar1:.2f}↔{ar2:.2f}"
    diff = float(np.abs(t1 - t2).mean())
    if diff > 0.30:
        return False, f"실루엣 차이 {diff:.2f}"
    return True, f"ok {diff:.2f}"


def targets(limit, only=None):
    raw = json.loads((C / "brands.json").read_text())
    br = raw["brands"] if isinstance(raw, dict) else raw
    byid = {b["id"]: b for b in br}
    want = json.loads((C / "svg-wanted.json").read_text())
    out = []
    for w in want:
        b = byid.get(w["id"])
        if not b or b.get("has_svg") or b.get("hidden"):
            continue
        if only and b["id"] not in only:
            continue
        site = b.get("website") or (f"https://{b['domain']}" if b.get("domain") else None)
        if not site:
            continue
        out.append({"id": b["id"], "name": b.get("name_ko") or b.get("name_en"), "site": site})
        if limit and len(out) >= limit:
            break
    return out


async def run(a):
    todo = targets(a.limit, set(a.ids.split(",")) if a.ids else None)
    print(f"대상 {len(todo)}건 (PNG 로 서비스 중 · 홈페이지 있음)\n")
    exe = ckr._find_browser()
    if not exe:
        print("❌ 브라우저 없음"); return
    from playwright.async_api import async_playwright
    hit = miss = review = 0
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
            # ⚠️ 사이트가 **다른 로고**를 SVG 로 주는 경우가 있다 — 모회사(tve→rtve),
            #    파트너(magxiv→pixiv), 같은 시장 타 방송국(kvhp→KPLC), hulu·SKS 등.
            #    2026-09-04 승격 28건 중 8건(29%)이 이랬다. accept() 는 '로고답냐'만
            #    보고 '이 브랜드냐'는 못 본다. 우리는 **기존 PNG 를 이미 갖고 있으니**
            #    새 SVG 렌더와 모양을 비교한다. 형태가 다르면(아이콘↔워드마크 포함)
            #    승격하지 않는다 — PNG 는 그대로 남으므로 잃는 것이 없다.
            ok_shape, why_shape = _same_shape(C / x["id"] / "logo.png", data)
            if not ok_shape:
                # 정답셋 검증(2026-09-04): 틀린 8건 중 7건을 잡지만 **정상 20건 중 12건도
                # 버린다** — 아이콘 PNG↔워드마크 SVG 같은 '같은 브랜드 다른 형태'를
                # 모양으로는 못 가른다. 그래서 버리지 않고 **검토 큐**에 넣는다.
                # 시트로 눈검사한 뒤 promote-reviewed.py 로 올린다.
                if not a.dry_run:
                    REVIEW.mkdir(exist_ok=True)
                    (REVIEW / (x["id"] + ".svg")).write_bytes(data)
                print(f"   {x['name'][:14]:<16} 🔎 검토큐({why_shape})"); review += 1; continue
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
    print(f"\n  벡터 확보 {hit} · 검토큐 {review} · 실패 {miss}  ({hit/max(1,hit+miss+review)*100:.0f}%)")
    if review:
        print("  검토: 시트로 눈검사 → scripts/promote-reviewed.py <id,...>")
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
    ap.add_argument("--ids", help="쉼표로 구분한 id 만 (가드 검증용)")
    asyncio.run(run(ap.parse_args()))
