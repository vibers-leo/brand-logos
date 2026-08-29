#!/usr/bin/env python3
"""국내 수집 대상 명단을 만든다. 수집기들이 이 파일을 읽는다.

⚠️ 예전에는 명단을 /tmp 에 두고 세션 안에서만 썼다. CI 는 매번 빈 러너라
   그 파일이 없고, 수집기가 **조용히 0건**을 내고 끝났다(에러도 안 난다).
   명단은 저장소 `_targets/` 에 두고 여기서 갱신한다.

출처:
  상장사   KRX 상장법인목록 — 회사명·종목코드·업종·홈페이지가 다 들어 있다
  지자체   위키데이터. ⚠️ 반드시 **상위 시도와 함께** 뽑는다 —
           '중구'가 6개, '동구'가 6개다. 이름만 쓰면 하나만 남고 나머지가
           통째로 사라진다(실제로 남구가 광주 것만 들어왔었다).
  기타     언론사·스포츠구단은 수집기가 직접 위키데이터를 부른다

  python3 scripts/kr-build-targets.py
"""
import json
import html as H
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_targets"
UA = "VibersLogoCollector/1.0 (https://semologo.com)"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
KRX = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
SIDO = {"서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시",
        "울산광역시", "세종특별자치시", "경기도", "강원특별자치도", "충청북도", "충청남도",
        "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도"}


def get(url, timeout=90, limit=8_000_000):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}),
        timeout=timeout, context=CTX).read(limit)


def krx():
    txt = get(KRX).decode("euc-kr", "ignore")
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", txt, re.S):
        td = [H.unescape(re.sub(r"<[^>]+>", "", c)).strip()
              for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(td) >= 9 and td[0]:
            out.append({"name": td[0], "market": td[1], "code": td[2],
                        "sector": td[3], "site": td[8]})
    if len(out) < 2000:
        raise SystemExit(f"KRX 목록이 {len(out)}건뿐이다 — 형식이 바뀌었을 수 있다")
    return out


def sparql(q, timeout=150):
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q})
    r = urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"}),
        timeout=timeout, context=CTX)
    return json.loads(r.read())["results"]["bindings"]


def muni():
    q = ('SELECT ?itemLabel ?parentLabel ?site WHERE { '
         '?item wdt:P17 wd:Q884 ; wdt:P131 ?parent . ?parent wdt:P17 wd:Q884 . '
         '?item rdfs:label ?l . FILTER(LANG(?l)="ko") FILTER(REGEX(?l,"(시|군|구)$")) '
         '?parent rdfs:label ?pl . FILTER(LANG(?pl)="ko") '
         'OPTIONAL { ?item wdt:P856 ?site } '
         'SERVICE wikibase:label { bd:serviceParam wikibase:language "ko". } } LIMIT 600')
    seen = {}
    for x in sparql(q):
        nm, par = x["itemLabel"]["value"], x["parentLabel"]["value"]
        if re.fullmatch(r"Q\d+", nm) or par not in SIDO:
            continue
        if not re.search(r"(시|군|구)$", nm) or len(nm) > 8:
            continue
        site = x.get("site", {}).get("value", "")
        k = (par, nm)
        if k not in seen or (site and not seen[k]):
            seen[k] = site

    from collections import Counter
    cnt = Counter(n for _, n in seen)
    rows = []
    for (par, nm), site in sorted(seen.items()):
        if not site:
            continue
        # 영문 페이지를 한글 메인으로 되돌린다 — 영문판은 로고가 다를 수 있다
        s = re.sub(r"/(site/)?(foreign|english|eng)(/.*)?$", "/", site, flags=re.I)
        s = re.sub(r"^(https?://)(english|eng)\.", r"\1www.", s, flags=re.I)
        # 동명일 때만 시도를 붙인다. 유일하면 그대로 — '서울특별시 강남구'는 장황하다
        rows.append({"name": f"{par} {nm}" if cnt[nm] > 1 else nm,
                     "short": nm, "sido": par, "site": s})
    if len(rows) < 150:
        raise SystemExit(f"지자체가 {len(rows)}건뿐이다 — 쿼리를 확인할 것")
    return rows


def franchise():
    """공정거래위원회 가맹사업 정보공개서 — 국내 프랜차이즈 전 브랜드.

    ⚠️ 이 목록에는 **홈페이지가 없다.** 상장사(KRX)와 다른 점이다.
       상세 페이지는 암호화 키와 세션이 필요한데 접근이 계속 실패했고,
       네이버 검색 API 키는 4개 모두 인증 실패였다(2026-08-29).
       그래서 명단만 확보해 둔다 — 로고 확보 경로가 열리면 바로 쓴다.
       다시 훑는 데 12페이지 요청이 드니 버리지 않는다.
    """
    import subprocess
    rows = {}
    for i in range(1, 15):
        d = (f"column=&searchKeyword=&selIndus=&selUpjong="
             f"&pageUnit=1000&pageIndex={i}")
        out = subprocess.run(
            ["curl", "-s", "--max-time", "90", "-A", UA, "-X", "POST", "--data", d,
             "https://franchise.ftc.go.kr/mnu/00013/program/userRqst/list.do"],
            capture_output=True).stdout.decode("utf-8", "ignore")
        got = 0
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", out, re.S):
            td = [H.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                  for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
            if len(td) >= 5 and td[0].isdigit():
                rows[td[0]] = {"no": td[0], "hq": td[1], "brand": td[2],
                               "ceo": td[3], "reg": td[4]}
                got += 1
        if not got:
            break
    if len(rows) < 5000:
        raise SystemExit(f"프랜차이즈가 {len(rows)}건뿐이다 — 형식을 확인할 것")
    return sorted(rows.values(), key=lambda x: -int(x["no"]))


def main():
    OUT.mkdir(exist_ok=True)
    k = krx()
    (OUT / "krx.json").write_text(json.dumps(k, ensure_ascii=False))
    print(f"  상장사 {len(k):,}건")
    m = muni()
    (OUT / "sgg-targets.json").write_text(json.dumps(m, ensure_ascii=False))
    amb = sum(1 for r in m if r["name"] != r["short"])
    print(f"  지자체 {len(m):,}건 (동명 시도병기 {amb}건)")
    try:
        f = franchise()
        (OUT / "franchise.json").write_text(json.dumps(f, ensure_ascii=False))
        print(f"  프랜차이즈 {len(f):,}건 (홈페이지 없음 — 명단만)")
    except SystemExit as e:
        print(f"  ⚠️ 프랜차이즈 건너뜀: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
