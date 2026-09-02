#!/usr/bin/env python3
"""네이버 검색으로 회사의 **공식 홈페이지**를 찾는다.

상장사 명단 2,802개 중 홈페이지가 비어 있는 것이 많고, 그게 수집 실패의
절반(no_site 47%)을 차지한다. 검색으로 메운다.

⚠️ **검색 1등을 그냥 믿으면 안 된다.** 2026-08-29 프랜차이즈 수집이 그렇게
   실패했다 — 1등이 창업뉴스·위키·전혀 다른 회사였다. 가드를 세 겹 건다:

   ① 도메인 반복  같은 도메인이 상위에 여러 번 나와야 그 회사 사이트다
                 (뉴스·블로그는 회사마다 다른 기사를 내보내므로 반복되지 않는다)
   ② 차단 목록    뉴스·위키·쇼핑·SNS·구인 사이트는 후보에서 뺀다
   ③ 실제 접속    열어서 회사 이름이 페이지에 있는지 확인한다

  python3 scripts/find-official-site.py --limit 50 --dry-run
  python3 scripts/find-official-site.py --limit 300 --apply
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import collect_krx_lib as L

TARGETS = Path(__file__).resolve().parent.parent / "_targets" / "krx.json"

# 회사 공식 사이트일 수 없는 곳
DENY = re.compile(
    r"(naver|daum|kakao|google|youtube|facebook|instagram|twitter|linkedin|tistory|"
    r"blog\.|cafe\.|news|press|wiki|namu\.wiki|"
    # 채용·기업리뷰 사이트. 회사를 검색하면 상위에 잘 나오고 회사명도 페이지에
    # 있어서 '이름 확인'까지 통과해 버린다(닷밀 → jobplanet 오답).
    r"jobkorea|saramin|incruit|wanted\.co|jobplanet|blind|teamblind|rocketpunch|"
    # 채용·IR 서브도메인은 본사 사이트가 아니다
    r"^(careers?|recruit|jobs|ir)\.|\.careers?\.|\.recruit\.|"
    r"catch\.co\.kr|thevc|innoforest|zuzu\.network|dart\.fss|krx\.co\.kr|"
    r"11st|coupang|gmarket|auction|interpark|smartstore|shopping|"
    r"youtu\.be|linktr\.ee|notion\.site|medium\.com|brunch|"
    # 주식 정보 사이트 — 상장사를 검색하면 회사 사이트보다 먼저 나오고,
    # 여러 회사가 같은 도메인을 공유하므로 '반복' 가드도 통과해 버린다.
    r"ipostock|38\.co\.kr|thinkpool|stockplus|paxnet|finance|invest|"
    r"seibro|kind\.krx|itooza|hankyung|mk\.co\.kr|edaily|infostock|"
    # 맛집·배달·프랜차이즈 중개 사이트 — 브랜드를 검색하면 공식 홈페이지보다
    # 먼저 나오고 브랜드명도 페이지에 있어 '이름 확인'까지 통과한다.
    r"diningcode|siksinhot|mangoplate|yogiyo|baemin|coupangeats|"
    r"menupan|foodsafetykorea|frandoor|bizk\.co\.kr|changupmall|"
    r"창업|franchise-?(info|mall)|startbiz|kfranchise)", re.I)

# 스팩(기업인수목적회사)은 껍데기라 홈페이지도 로고도 없다.
# 홈페이지 미보유 177건 중 69건(39%)이 스팩이었다 — 검색 비용만 든다.
SKIP_NAME = re.compile(r"스팩|기업인수목적|제\d+호")

def host(u):
    return re.sub(r"^https?://(www\.)?", "", (u or "")).split("/")[0].lower()

def search(q, n=10):
    url = ("https://naverapihub.apigw.ntruss.com/search/v1/webkr?"
           + urllib.parse.urlencode({"query": q, "display": n}))
    req = urllib.request.Request(url, headers={
        "X-NCP-APIGW-API-KEY-ID": os.environ["NAVER_APIHUB_CLIENT_ID"],
        "X-NCP-APIGW-API-KEY": os.environ["NAVER_APIHUB_CLIENT_SECRET"]})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("items", [])

def norm(s):
    return re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())

def candidates(items, k=3):
    """상위 후보 도메인을 반복 횟수 순으로 최대 k개.

    ⚠️ 처음엔 '반복 2회 이상'만 채택했는데 **정답을 대부분 버렸다** —
       naraspace.com(나라스페이스)·thepinkfongcompany.com·g2gbio.com 이
       모두 1회라 탈락했다. 회사가 작을수록 검색 결과가 흩어지기 때문이다.
       반복은 참고 신호로만 두고, 판정은 **실제 접속 후 이름 확인**에 맡긴다.
    """
    hosts = [host(it.get("link")) for it in items]
    hosts = [h for h in hosts if h and not DENY.search(h)]
    if not hosts:
        return []
    cnt = Counter(hosts)
    return [(h, n) for h, n in cnt.most_common(k)]

def verify(domain, name):
    """실제로 열어 회사 이름이 페이지에 있는지 본다.

    이것이 유일하게 믿을 만한 판정이다. 검색 순위·반복 횟수는 참고일 뿐
    '닷밀 → jobplanet.co.kr' 같은 오답을 못 막는다.

    반환: (url, "확인") | (url, "약함") | (None, 사유)
      확인 = 페이지에 회사 이름이 있다. 바로 채택한다.
      약함 = 접속은 되나 이름이 없다(영문 전용 사이트). 반복 2회 이상일 때만 채택.
    """
    for scheme in ("https://", "http://"):
        try:
            html, _ = L.get_text(scheme + domain, timeout=12)
        except Exception:
            continue
        n = norm(name)
        body = norm(html[:80000])
        if n and n in body:
            return scheme + domain, "확인"
        # 회사명 앞 4글자만이라도 걸리면 준하는 신호로 본다
        if len(n) >= 5 and n[:4] in body:
            return scheme + domain, "확인"
        return scheme + domain, "약함"
    return None, "접속 실패"

def main():
    apply_ = "--apply" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 50
    rows = json.loads(TARGETS.read_text())
    todo = [r for r in rows
            if not (r.get("site") or "").strip() and not SKIP_NAME.search(r["name"])]
    print(f"  홈페이지 없음 {len(todo):,}건 · 이번 {min(limit,len(todo))}건")
    found = skip = 0
    for r in todo[:limit]:
        try:
            items = search(r["name"])
        except Exception as e:
            print(f"   {r['name'][:14]:<16} 검색 실패 {type(e).__name__}"); continue
        cands = candidates(items)
        if not cands:
            print(f"   {r['name'][:14]:<16} — 후보 없음"); skip += 1; time.sleep(0.3); continue
        chosen = None
        for dom, n in cands:
            url, vwhy = verify(dom, r["name"])
            if not url:
                continue
            # ⚠️ '약함'(접속만 되고 이름 없음)은 채택하지 않는다.
            #    반복 2회를 근거로 받아들였더니 jobplanet 같은 오답이 통과했다.
            #    이름이 확인된 것만 쓴다 — 놓치는 편이 틀리는 것보다 낫다.
            if vwhy == "확인":
                chosen = (url, f"{dom}×{n} · {vwhy}")
                break
        if not chosen:
            print(f"   {r['name'][:14]:<16} — 검증 실패 ({cands[0][0]})"); skip += 1; time.sleep(0.3); continue
        print(f"   {r['name'][:14]:<16} ✅ {chosen[0][:42]}  [{chosen[1]}]")
        r["site"] = chosen[0]
        r["site_source"] = "naver-search"
        found += 1
        time.sleep(0.3)
    print(f"\n  찾음 {found} · 실패 {skip}")
    if apply_ and found:
        TARGETS.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
        print("  ✅ _targets/krx.json 갱신")

main()
