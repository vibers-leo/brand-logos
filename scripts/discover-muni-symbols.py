#!/usr/bin/env python3
"""지자체 공식 상징물 페이지·배포 파일을 **찾아서 목록으로 만든다**.

⚠️ 자동 등록은 하지 않는다. 왜 그런지가 이 파일의 요점이다.

■ 무엇이 되나 (2026-08-30 실측)
  · 홈에서 상징물 페이지 링크 찾기 — 40곳 중 10곳(25%)
    '국가상징'(행안부 태극기 팝업)은 오답이라 걸러야 한다
  · 그 페이지에서 CI 배포 파일(zip/ai) 찾기 — 성남시 Ci_AI.zip(15MB) 확보
    심볼마크·로고타입·시그니처·엠블럼이 부산과 같은 체계로 들어 있다

■ 무엇이 안 되나 — 여기서 멈춘 이유
  성남 Ci_AI.zip 을 열어보니 **로고 파일이 아니라 CI 매뉴얼 페이지**였다.
  한 장에 심볼마크 + 그리드 + 최소크기 규정 + 최소공간 규정이 함께 있다.
  유채색 영역이 x57~293 · y124~507 로 여러 덩어리에 흩어져 있어
  자동 크롭하면 규정 예시나 금지사례를 로고로 집을 수 있다.

  부산은 로고만 담긴 파일을 배포했지만(그래서 자동 처리가 됐다)
  성남처럼 매뉴얼로 배포하는 곳이 더 많다. 배포 형태가 표준화돼 있지 않다.

■ 그래서 이 스크립트의 역할
  1) 상징물 페이지 URL 과 배포 파일 링크를 모아 목록을 만든다
  2) 사람은 그 목록을 보고 **파일 형태만 확인**하면 된다
     (로고만 담긴 것 → 자동 처리 / 매뉴얼 → 건너뜀)
  3) 자동 등록 여부는 파일을 열어본 뒤에 정한다

  python3 scripts/discover-muni-symbols.py --limit 40
  python3 scripts/discover-muni-symbols.py            # 전체 229곳
"""
import concurrent.futures as cf
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_krx_lib import get, get_text   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "_targets" / "sgg-targets.json"
OUT = ROOT / "_targets" / "muni-symbols.json"

# '국가상징'은 행정안전부 태극기 안내 팝업이다 — 지자체 상징물이 아니다
BAD = re.compile(r"mois\.go\.kr|국가상징|태극기")
KEY = re.compile(r"상징|심벌|심볼|캐릭터|마스코트|엠블럼")
NAV = re.compile(r"소개|시정|군정|구정|안내|정보")
ASSET = re.compile(r"\.(zip|ai|eps|pdf)(\?|$)", re.I)


def links(html, base):
    out = []
    for m in re.finditer(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        t = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        u = urllib.parse.urljoin(base, m.group(1))
        if BAD.search(u) or BAD.search(t):
            continue
        out.append((t, u))
    return out


# alt 로 상징물을 가려낸다. 한국 지자체는 웹접근성 의무로 alt 를 성실히 단다.
SYMBOL_ALT = re.compile(
    r"휘장|심볼|상징|엠블럼|마크|로고|캐릭터|마스코트|브랜드|슬로건|"
    r"시목|시화|시조|군목|군화|군조|구목|구화|구조|도목|도화|도조|CI|BI")
# 인증마크·SNS·배너처럼 상징물이 아닌 것
NOISE_ALT = re.compile(
    r"웹접근성|접근성 인증|WA인증|품질인증|웹와치|QR|큐알|바로가기|"
    r"페이스북|인스타|유튜브|트위터|카카오|블로그|배너|팝업|이전|다음|"
    r"홈페이지 로고|사이트 로고|공공누리|공공저작물|KOGL|태극기|국기|"
    # 시목·시화·시조는 alt 에 상징어가 들어가지만 실제로는 **나무·꽃·새 사진**이다.
    # 사진 판정(ink_ratio -3.0)이 뒤에서 걸러 주지만 여기서 미리 빼면
    # 받아 보는 비용을 아낀다. 사진이 아닌 도안이면 다른 alt 로 또 잡힌다.
    r"사진|photo")


def work(r):
    rec = {"name": r["name"], "site": r["site"], "page": None,
           "page_label": None, "assets": [], "status": ""}
    try:
        h = get_text(r["site"], timeout=12)[0]
    except Exception as e:
        rec["status"] = f"접속실패:{type(e).__name__}"
        return rec

    ls = links(h, r["site"])
    hit = [(t, u) for t, u in ls if 1 < len(t) < 24 and KEY.search(t)]
    if not hit:
        # 소개·시정 메뉴 한 단계 더 들어간다
        for t, u in ls[:60]:
            if not (1 < len(t) < 16 and NAV.search(t)):
                continue
            try:
                h2 = get_text(u, timeout=10)[0]
            except Exception:
                continue
            hit = [(a, b) for a, b in links(h2, u) if 1 < len(a) < 24 and KEY.search(a)]
            if hit:
                break
    if not hit:
        # ③ 흔한 URL 을 직접 찔러본다.
        #    이미 찾은 105곳의 URL 패턴을 세보니 /symbol 이 12곳으로 가장 많았다.
        #    사이트맵도 봤지만 실용성이 낮았다 — 홍천군은 4,099 URL 이라 전부
        #    열 수 없고, 문자열로 거르면 'sciencecenter' 의 ci 같은 오답이 쏟아진다.
        base = r["site"].rstrip("/")
        for path in ("/symbol", "/kr/symbol", "/www/symbol", "/portal/symbol",
                     "/symbol.do", "/ci", "/kr/ci", "/intro/symbol",
                     "/introduction/symbol", "/about/symbol"):
            try:
                hb = get_text(base + path, timeout=8, limit=120000)[0]
            except Exception:
                continue
            # 실제 상징물 페이지인지 본문으로 확인한다 — 404 페이지도 200 을 준다
            body = re.sub(r"<[^>]+>", " ", hb)
            if len(re.findall(r"심벌|심볼|상징|마크|캐릭터|마스코트", body)) >= 2:
                hit = [("직접경로" + path, base + path)]
                break

    if not hit:
        rec["status"] = "상징물 페이지 못 찾음"
        return rec

    rec["page_label"], rec["page"] = hit[0]
    try:
        hp = get_text(rec["page"], timeout=15)[0]
    except Exception as e:
        rec["status"] = f"페이지실패:{type(e).__name__}"
        return rec

    for m in re.finditer(r'href="([^"]+)"', hp):
        u = urllib.parse.urljoin(rec["page"], m.group(1))
        if ASSET.search(u) and "favicon" not in u.lower():
            rec["assets"].append(u)

    # ⚠️ href 만 보면 **페이지에 박힌 로고 이미지를 통째로 놓친다.**
    #    구리시 휘장은 `cts416_img.png` 라 파일명에 logo·symbol 이 없고
    #    다운로드 링크도 없다. 그런데 alt 는 "시 휘장 이미지" 로 정확하다.
    #    한국 지자체는 웹접근성 의무 때문에 alt 를 성실히 단다 — 파일명보다
    #    alt 가 훨씬 믿을 만한 분류 신호다.
    rec["images"] = []
    for m in re.finditer(r"<img\b[^>]*>", hp, re.I):
        tag = m.group(0)
        src = re.search(r'src="([^"]+)"', tag, re.I)
        alt = re.search(r'alt="([^"]*)"', tag, re.I)
        if not src: continue
        a = (alt.group(1) if alt else "").strip()
        if not SYMBOL_ALT.search(a): continue
        if NOISE_ALT.search(a): continue
        rec["images"].append({"src": urllib.parse.urljoin(rec["page"], src.group(1)),
                              "alt": a[:60]})
    rec["images"] = rec["images"][:12]

    rec["assets"] = list(dict.fromkeys(rec["assets"]))[:8]
    if rec["images"]:
        rec["status"] = "이미지 있음" + (" + 배포파일" if rec["assets"] else "")
    else:
        rec["status"] = "배포파일 있음" if rec["assets"] else "페이지만 있음"
    return rec


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    rows = json.loads(TARGETS.read_text())
    if limit:
        rows = rows[:limit]
    res = []
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for i, rec in enumerate(ex.map(work, rows), 1):
            res.append(rec)
            if i % 40 == 0:
                print(f"  {i}/{len(rows)}", flush=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    from collections import Counter
    c = Counter(r["status"].split(":")[0] for r in res)
    print(f"\n✅ {len(res)}곳 조사 → {OUT.name}")
    for k, v in c.most_common():
        print(f"   {k:<18} {v}")
    withasset = [r for r in res if r["assets"]]
    print(f"\n   배포파일 확보 {len(withasset)}곳:")
    for r in withasset[:12]:
        print(f"     {r['name'][:14]:<16} {r['assets'][0][:58]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
