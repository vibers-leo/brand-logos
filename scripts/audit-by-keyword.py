#!/usr/bin/env python3
"""이름·도메인의 **강한 업종 키워드**로 카테고리 오분류를 찾는다.

위키데이터 설명문 교차검증(audit-categories.py)이 못 잡는 구멍이 있다.
NASA·SpaceX·ISRO 는 설명문이 아예 없어서 'IT·테크'에 그대로 남아 있었다.
QID 33,475개 중 설명문이 있는 건 24,090개뿐이다.

이름에 'aerospace'·'대학교'·'은행'처럼 업종이 박혀 있으면 설명문 없이도
판정할 수 있다. 대신 **거의 확실한 키워드만** 쓴다 — 애매하면 안 옮긴다.

  python3 scripts/audit-by-keyword.py
  python3 scripts/audit-by-keyword.py --apply
"""
import json, re, sys
from collections import Counter

# (카테고리, 정규식) — 이름·한글명·도메인을 합친 문자열에 건다.
# ⚠️ (?i) 를 패턴 중간에 쓰면 안 된다. 파이썬은 "global flags not at the
#    start" 로 죽는다. 대소문자 무시는 re.search 의 flags 로 준다.
RULES = [
 ("항공·우주·방산", r"\b(aerospace|astronaut|cosmonaut|spacecraft|"
                r"space (agency|center|centre|program|mission|force|command)|"
                r"defen[sc]e (industr|systems|company))\b|항공우주|우주항공|방위산업"),
 ("교육", r"대학교$|대학원|고등학교$|중학교$|초등학교$|"
        r"\b(university|universit[äa]t|universidad|college of|"
        r"school of (business|law|medicine|engineering))\b"),
 ("의료·바이오", r"병원$|의료원$|보건소$|치과$|한의원$|"
              r"\b(hospital|medical cent(er|re)|pharmaceutical)\b"),
 ("금융·결제", r"은행$|저축은행$|증권$|화재해상보험|생명보험$|손해보험$|카드$|캐피탈$|"
             r"\b(bank$|banking corp|securities co|life insurance)\b"),
 ("물류·교통", r"항공$|공항$|철도$|고속도로$|해운$|택배$|"
             r"\b(air ?lines?$|airways$|international airport|"
             r"railways?$|logistics$)\b"),
 ("미디어·엔터", r"방송$|신문$|일보$|텔레비전$|엔터테인먼트$|"
              r"\b(broadcasting (system|corp)|television network)\b"),
 ("통신", r"\b(telecom(munications?)?$|mobile (network|telecom))\b|통신$"),
 ("에너지·화학", r"전력$|발전$|가스공사|석유화학$|정유$|"
              r"\b(electric power (co|corp)|petrochemical)\b"),
 ("스포츠", r"\b(football club$|f\.?c\.?$|olympic (committee|games)|"
          r"athletic club$)\b|축구단$|야구단$|구단$"),
]

# 이름에 업종어가 들어 있지만 그 업종이 아닌 것들. 눈으로 확인해 박아 둔다.
EXCEPT = {
 "mission-space":        "디즈니월드 놀이기구",
 "monsters-university":  "디즈니 영화",
 "hospital-records":     "영국 드럼앤베이스 음반 레이블",
 "college-of-arms":      "영국 문장원 — 학교가 아니다",
 "swiss-university-sports": "대학 스포츠 연맹 — 스포츠가 맞다",
}

# 도메인 TLD 는 설명문보다 강한 신호다. .gov·.go.kr 은 정부기관이 아닐 수 없다.
# 설명문이 'company' 뿐이라 규칙에 안 걸리던 87건을 여기서 건진다.
TLD_RULES = [
 ("공공·기관", r"\.(gov|gov\.[a-z]{2}|go\.kr|mil|mil\.[a-z]{2})$"),
 ("교육", r"\.(edu|edu\.[a-z]{2}|ac\.[a-z]{2})$"),
]


def domain_of(b):
    s = (b.get("domain") or b.get("website") or "").lower()
    return re.sub(r"^https?://", "", s).split("/")[0].removeprefix("www.")


def main():
    d = json.load(open("_clients/brands.json"))["brands"]
    hits = []
    for b in d:
        cur = b.get("category")
        if b.get("category_src") == "manual": continue
        if b["id"] in EXCEPT: continue
        t = " ".join(str(x) for x in
                     (b.get("name_en"), b.get("name_ko"), b.get("domain")) if x)
        matched = False
        for cat, pat in RULES:
            if cat == cur: break
            if re.search(pat, t, re.I):
                hits.append((b["id"], b.get("name_ko"), cur, cat, t[:44]))
                matched = True; break
        if matched: continue
        # ⚠️ TLD 는 **'기타'에서만** 쓴다. 이미 분류된 것에 적용하면
        #    NASA(.gov)가 '항공·우주·방산' → '공공·기관' 으로, 지자체(.go.kr)가
        #    '국가·지역' → '공공·기관' 으로 끌려간다. 정부 도메인을 쓴다고
        #    업종이 정부기관인 건 아니다.
        if cur != "기타": continue
        dm = domain_of(b)
        if not dm: continue
        for cat, pat in TLD_RULES:
            if cat == cur: break
            if re.search(pat, dm):
                hits.append((b["id"], b.get("name_ko"), cur, cat, dm[:40])); break
    print(f"  어긋남 {len(hits)}건")
    for (a, bb), k in Counter((h[2], h[3]) for h in hits).most_common(12):
        print(f"     {str(a):<14} → {bb:<14} {k}")
    if "--list" in sys.argv:
        for h in hits[:70]:
            print(f"   {h[0][:22]:<24} {str(h[1])[:16]:<18} {str(h[2]):<12} → {h[3]:<12} {h[4]}")
    if "--apply" in sys.argv:
        doc = json.load(open("_clients/brands.json"))
        m = {h[0]: h[3] for h in hits}; n = 0
        for b in doc["brands"]:
            if b["id"] in m:
                b["category"] = m[b["id"]]; b["category_src"] = "keyword-audit"; n += 1
        json.dump(doc, open("_clients/brands.json", "w"),
                  ensure_ascii=False, separators=(",", ":"))
        print(f"  ✅ {n}건 이동")

main()
