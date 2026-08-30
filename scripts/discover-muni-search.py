#!/usr/bin/env python3
"""검색으로 지자체 상징물 페이지를 직접 찾는다.

■ 왜 이 방법인가
홈에서 링크를 타는 방식은 두 번 막혔다:
  정적 크롤링   229곳 중 113곳 실패 — 메뉴가 JS 로 그려진다
  브라우저 렌더  123곳 중 61곳 여전히 실패 — 홈에 링크가 없다(메뉴 깊이)
검색은 그 페이지를 **바로** 안다. 실측:
  삼척시 → '심벌마크(SYMBOL)' /intro/00362/01443.web
  철원군 → '상징물' /www/contents.do?key=235

■ 프랜차이즈에서 검색이 실패했던 것과 다르다
그때는 창업 중개 사이트가 결과를 뒤덮었다. 지자체는 **공식 도메인이 정해져
있어서**(명단의 site) 같은 호스트 결과만 남기면 오답이 거의 없다.

⚠️ 의회(council.*)는 제외한다. '상징물 조례'가 상위에 잡히는데
   그건 법령 문서지 로고 페이지가 아니다(정선군에서 실제로 나왔다).

  python3 scripts/discover-muni-search.py --limit 10
  python3 scripts/discover-muni-search.py
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REND = ROOT / "_targets" / "muni-symbols-rendered.json"
SYM = ROOT / "_targets" / "muni-symbols.json"
OUT = ROOT / "_targets" / "muni-symbols-search.json"
HUB = "https://naverapihub.apigw.ntruss.com/search/v1/webkr"
ASSET = re.compile(r"\.(zip|ai|eps|pdf)(\?|$)", re.I)
# 의회·조례는 로고 페이지가 아니다
BAD = re.compile(r"council\.|/assembly|조례|규칙|법령|의회", re.I)
GOOD = re.compile(r"상징|심벌|심볼|캐릭터|마스코트|엠블럼|CI\b", re.I)


def hub(q, n=10):
    i, s = os.environ.get("NAVER_APIHUB_CLIENT_ID"), os.environ.get("NAVER_APIHUB_CLIENT_SECRET")
    if not i or not s:
        raise SystemExit("NAVER_APIHUB_CLIENT_ID / SECRET 없음 — .secrets 를 source 할 것")
    u = f"{HUB}?query={urllib.parse.quote(q)}&display={n}"
    r = urllib.request.urlopen(urllib.request.Request(
        u, headers={"X-NCP-APIGW-API-KEY-ID": i, "X-NCP-APIGW-API-KEY": s}), timeout=20)
    return json.loads(r.read()).get("items", [])


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    rend = json.loads(REND.read_text()) if REND.exists() else []
    todo = [r for r in rend if r["status"].startswith(("렌더해도", "실패"))]
    # 명단의 최신 URL 을 쓴다 — 그동안 교정됐을 수 있다
    tg = {r["name"]: r["site"] for r in json.loads((ROOT/"_targets"/"sgg-targets.json").read_text())}
    for r in todo:
        r["site"] = tg.get(r["name"], r["site"])
    if limit:
        todo = todo[:limit]
    print(f"검색 대상 {len(todo)}곳", flush=True)

    res = []
    for i, r in enumerate(todo, 1):
        host = re.sub(r"^https?://(www\.)?|/.*$", "", r["site"]).lower()
        rec = {"name": r["name"], "site": r["site"], "page": None,
               "page_label": None, "assets": [], "status": "검색 실패"}
        for q in (f"{r['name']} 상징물 심벌마크", f"{r['name']} CI 캐릭터"):
            try:
                items = hub(q)
            except SystemExit:
                raise
            except Exception:
                continue
            for x in items:
                link = x.get("link") or ""
                if host not in link or BAD.search(link):
                    continue
                title = re.sub(r"<[^>]+>", "", x.get("title") or "")
                if not GOOD.search(title) and not GOOD.search(link):
                    continue
                rec["page"], rec["page_label"] = link, title[:30]
                rec["status"] = "페이지만 있음"
                break
            if rec["page"]:
                break
            time.sleep(0.25)
        res.append(rec)
        if i % 20 == 0:
            print(f"  {i}/{len(todo)} · 발견 {sum(1 for x in res if x['page'])}", flush=True)
        time.sleep(0.2)

    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    found = [r for r in res if r["page"]]
    print(f"\n✅ {len(res)}곳 → {OUT.name}")
    print(f"   상징물 페이지 발견 {len(found)}곳")
    for r in found[:12]:
        print(f"     {r['name'][:14]:<16} [{r['page_label'][:16]:<16}] {r['page'][:44]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
