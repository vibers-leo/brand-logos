#!/usr/bin/env python3
"""브라우저로 렌더해서 지자체 상징물 페이지를 찾는다.

■ 왜 필요한가
정적 크롤링(discover-muni-symbols.py)이 229곳 중 113곳에서 실패했다.
원인은 사이트가 죽어서가 아니라 **메뉴가 JS 로 그려지기 때문**이다:
  양양군·원주시  a 태그 0개
  강릉시·삼척시  a 태그 4~11개 (껍데기만)
원주시는 렌더하니 a 태그가 0 → 1,459 개가 되고 '원주의 상징' 링크가 나왔다.

■ 한계도 분명하다
렌더해도 홈에 상징물 링크가 없는 곳이 있다(6곳 시험에서 1곳만 발견).
그런 곳은 메뉴 depth 가 깊다 — 그래서 '소개·시정' 메뉴를 한 단계 더 들어간다.

■ 기존 브라우저를 쓴다
playwright install 은 수백 MB 를 받는다. 이미 받아둔 chromium-1234 를
executable_path 로 지정한다.

  python3 scripts/discover-muni-rendered.py --limit 10
  python3 scripts/discover-muni-rendered.py
"""
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYM = ROOT / "_targets" / "muni-symbols.json"
OUT = ROOT / "_targets" / "muni-symbols-rendered.json"
EXE = ("/Users/juuuno/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
       "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")

KEY = ("상징", "심벌", "심볼", "캐릭터", "마스코트", "엠블럼")
NAV = ("소개", "시정", "군정", "구정", "안내", "정보", "알아보기", "열린")
BAD = re.compile(r"mois\.go\.kr|국가상징|태극기")
ASSET = re.compile(r"\.(zip|ai|eps|pdf)(\?|$)", re.I)


def pick(links):
    out = []
    for t, u in links:
        if not t or not u or BAD.search(u) or BAD.search(t):
            continue
        t = t.strip()
        if 1 < len(t) < 24 and any(k in t for k in KEY):
            out.append((t, u))
    return out


async def scan(page, url, wait=1600):
    await page.goto(url, timeout=25000, wait_until="domcontentloaded")
    await page.wait_for_timeout(wait)
    return await page.eval_on_selector_all(
        "a", "els=>els.map(e=>[e.innerText.trim(), e.href])")


async def work(browser, r):
    rec = {"name": r["name"], "site": r["site"], "page": None,
           "page_label": None, "assets": [], "status": ""}
    pg = await browser.new_page()
    try:
        links = await scan(pg, r["site"])
        hit = pick(links)
        if not hit:
            # 소개·시정 메뉴 한 단계 더
            navs = [(t, u) for t, u in links
                    if t and 1 < len(t.strip()) < 16 and any(k in t for k in NAV)][:5]
            for t, u in navs:
                try:
                    hit = pick(await scan(pg, u, 1200))
                except Exception:
                    continue
                if hit:
                    break
        if not hit:
            rec["status"] = "렌더해도 못 찾음"
            return rec

        rec["page_label"], rec["page"] = hit[0]
        await pg.goto(rec["page"], timeout=25000, wait_until="domcontentloaded")
        await pg.wait_for_timeout(1500)
        hrefs = await pg.eval_on_selector_all("a", "els=>els.map(e=>e.href)")
        rec["assets"] = list(dict.fromkeys(
            u for u in hrefs if u and ASSET.search(u) and "favicon" not in u.lower()))[:8]
        rec["status"] = "배포파일 있음" if rec["assets"] else "페이지만 있음"
    except Exception as e:
        rec["status"] = f"실패:{type(e).__name__}"
    finally:
        await pg.close()
    return rec


async def main():
    from playwright.async_api import async_playwright
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    recs = json.loads(SYM.read_text())
    todo = [r for r in recs if r["status"] in ("상징물 페이지 못 찾음",)
            or r["status"].startswith("접속실패")]
    if limit:
        todo = todo[:limit]
    print(f"렌더 대상 {len(todo)}곳", flush=True)

    res = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch(executable_path=EXE)
        # 동시 4개 — 더 늘리면 지자체 서버가 끊는다
        sem = asyncio.Semaphore(4)

        async def guarded(r):
            async with sem:
                return await work(b, r)

        tasks = [asyncio.create_task(guarded(r)) for r in todo]
        for i, t in enumerate(asyncio.as_completed(tasks), 1):
            rec = await t
            res.append(rec)
            if i % 20 == 0:
                found = sum(1 for x in res if x["page"])
                print(f"  {i}/{len(todo)} · 발견 {found}", flush=True)
        await b.close()

    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    from collections import Counter
    c = Counter(r["status"].split(":")[0] for r in res)
    print(f"\n✅ {len(res)}곳 → {OUT.name}")
    for k, v in c.most_common():
        print(f"   {k:<18} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
