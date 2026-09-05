#!/usr/bin/env python3
"""국내 '금광' 타겟을 위키데이터에서 만든다 — 대학·병원·금융·언론·스포츠구단.

이 분야들은 공식 명단이 있고 홈페이지(P856)가 붙어 있어, 프랜차이즈처럼 검색으로
주소를 찍는 헛발질이 없다. 결과는 `_targets/{kind}.json` → collect-krx-rendered.py
의 SOURCES 가 그대로 먹는다.

  python3 scripts/build-kr-targets.py            # 전부
  python3 scripts/build-kr-targets.py univ       # 하나만
"""
import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
C, T = BASE / "_clients", BASE / "_targets"
UA = "semologo-kr-targets/1.0 (https://semologo.com; vibers.leo@gmail.com)"

# kind → [(QID, 라벨)] — P31/P279* 로 하위 클래스까지 훑는다
KINDS = {
    # ⚠️ QID 는 반드시 wbgetentities 로 라벨·설명을 확인한 것만 쓴다.
    #    2026-09-05 첫 판에서 5개가 엉터리였다 — 가상 국가·스페인 마을·은하·1996년 싱글·조경가.
    #    "Q4830453=자산운용사"라 적은 것은 실제로 '사업(business)'이라 한국 기업 1,070개를 끌어왔다.
    "univ":     [("Q3918", "대학"), ("Q189004", "전문대학"), ("Q1371037", "기술대학")],
    "hospital": [("Q16917", "병원"), ("Q1059324", "대학병원"), ("Q2440002", "종합병원")],
    "finance":  [("Q22687", "은행"), ("Q157963", "저축은행"), ("Q2143354", "보험회사"),
                 ("Q57774676", "카드사"), ("Q4230006", "자산운용사"), ("Q2073644", "증권·브로커")],
    "media":    [("Q11032", "신문"), ("Q1616075", "TV방송국"), ("Q14350", "라디오방송국"),
                 ("Q1110794", "일간지"), ("Q192283", "뉴스통신사")],
    "sports":   [("Q476028", "축구구단"), ("Q13027888", "야구팀"), ("Q13393265", "농구팀"),
                 ("Q15720476", "배구팀"), ("Q20639856", "프로스포츠팀")],
}
CAT = {"univ": "교육", "hospital": "의료·바이오", "finance": "금융·결제",
       "media": "미디어·엔터", "sports": "스포츠"}


def sparql(qid):
    q = f"""SELECT ?i ?l ?site WHERE {{
      ?i wdt:P31/wdt:P279* wd:{qid} .
      ?i wdt:P17 wd:Q884 .
      OPTIONAL {{ ?i wdt:P856 ?site }}
      ?i rdfs:label ?l FILTER(LANG(?l)="ko")
    }} LIMIT 3000"""
    data = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
    req = urllib.request.Request("https://query.wikidata.org/sparql", data=data,
        headers={"User-Agent": UA, "Accept": "application/sparql-results+json",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=180) as f:
        return json.load(f)["results"]["bindings"]


def dom(u):
    return re.sub(r"^https?://(www\.)?|/.*$", "", (u or "").strip()).lower()


def main(kinds):
    d = json.loads((C / "brands.json").read_text())
    br = d["brands"] if isinstance(d, dict) else d
    norm = lambda s: re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())
    known_name = {norm(b.get("name_ko")) for b in br} | {norm(b.get("name_en")) for b in br}
    known_wd = {b.get("wikidata") for b in br if b.get("wikidata")}
    known_dom = {dom(b.get("website") or b.get("domain")) for b in br}
    known_dom.discard("")

    for kind in kinds:
        seen, rows = set(), []
        for qid, label in KINDS[kind]:
            try:
                res = sparql(qid)
            except Exception as e:
                print(f"  {kind}/{label}: ❌ {type(e).__name__} {str(e)[:60]}"); time.sleep(3); continue
            n = 0
            for r in res:
                wd = r["i"]["value"].rsplit("/", 1)[-1]
                if wd in seen: continue
                seen.add(wd)
                site = r.get("site", {}).get("value", "")
                rows.append({"name": r["l"]["value"], "site": site, "wikidata": wd,
                             "sub": label, "cat": CAT[kind]})
                n += 1
            print(f"  {kind}/{label}: {len(res)}건 → 신규 {n}")
            time.sleep(1.5)
        # 보유분 제외: 이름·QID·도메인 셋 중 하나라도 겹치면 이미 있는 것
        todo = [r for r in rows if norm(r["name"]) not in known_name
                and r["wikidata"] not in known_wd and (not r["site"] or dom(r["site"]) not in known_dom)]
        withsite = [r for r in todo if r["site"]]
        out = T / f"{kind}.json"
        out.write_text(json.dumps(withsite, ensure_ascii=False, indent=1) + "\n")
        print(f"▶ {kind}: 전체 {len(rows):,} · 미보유 {len(todo):,} · 홈페이지 있음 {len(withsite):,} → {out.name}\n")


if __name__ == "__main__":
    ks = sys.argv[1:] or list(KINDS)
    main(ks)
