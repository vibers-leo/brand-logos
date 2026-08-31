#!/usr/bin/env python3
"""'기타' 로 남은 브랜드를 이름의 강한 신호로 재분류한다.

8,371개가 기타에 쌓여 있었다. 대부분 해외 브랜드라 수집 시점에
카테고리를 못 정한 것들이다.

**보수적으로 간다.** 애매하면 기타로 둔다 — 잘못 옮기면 사용자가
엉뚱한 카테고리에서 찾게 되고, 그건 안 옮긴 것보다 나쁘다.
그래서 단어 하나가 아니라 '그 단어가 나오면 거의 확실한' 것만 쓴다.
(예: 'group'·'holding' 은 어느 업종에나 있어 신호가 아니다)

  python3 scripts/recategorize-etc.py --dry-run
  python3 scripts/recategorize-etc.py --apply
"""
import json, re, sys

# 접미사·법인격은 신호가 아니다. 매칭 전에 떼어낸다.
NOISE = re.compile(r"\b(gmbh|ag|a\.?g\.?|s\.?a\.?|inc|ltd|limited|llc|plc|"
                   r"corporation|corp|company|co\.|holdings?|holding|group|gruppe|"
                   r"international|und|and|der|des|die|the)\b", re.I)

RULES = [
 # 정당·선거 캠페인 — 공공보다 미디어에 가깝지도 않아 별도로 앞에 둔다
 ("공공·기관", r"(presidential campaign|election campaign|political party|"
              r"\bparty\b.*\b(korea|germany|france|japan|america)\b)"),
 # BKK 는 독일 법정 건강보험조합이다 (64건). 이름에 거의 항상 접두로 붙는다
 ("의료·바이오", r"^bkk[ -]|\bbetriebskrankenkasse\b|\bkrankenkasse\b"),
 # RRI = Radio Republik Indonesia 지역국 (48건)
 ("미디어·엔터", r"^rri \b|radio republik"),
 # (카테고리, 정규식) — 위에서부터 먼저 맞는 것
 ("스포츠", r"\b(olympic|olympics|olympiad|paralympic|fifa|uefa|nba|nfl|mlb|nhl|"
            r"football[ -]?club|f\.?c\.?$|athletic|sportverein|stadium|marathon|"
            r"esports|e-sports|rugby|cricket|basketball|baseball|volleyball|"
            r"golf club|tennis|racing team|motogp|formula ?1)\b|올림픽|월드컵|프로야구|프로축구"),
 ("공공·기관", r"\b(ministry|ministerio|minist[eè]re|department of|city council|"
              r"county council|municipality|prefecture|governor|presidential|"
              r"government|parliament|senate|congress|embassy|consulate|"
              r"police|fire department|highway patrol|customs|"
              r"national (agency|authority|bureau|service|institute|library|archives)|"
              r"공사|공단|청$|부$|위원회|대사관|영사관|시청|군청|도청)\b"),
 ("교육", r"\b(university|universit[äa]t|universidad|universit[ée]|college|"
          r"school|schule|gymnasium|academy|akademie|institute of technology|"
          r"polytechnic)\b|대학교|학교|학원|교육원"),
 ("미디어·엔터", r"\b(broadcasting|broadcast|television|radio|tv$|studios?$|"
                r"records?$|film(s)?$|pictures$|entertainment|publishing|"
                r"magazine|newspaper|zeitung|verlag)\b|방송|신문|출판|엔터테인먼트"),
 ("에너지·화학", r"\b(stadtwerke|energie|energy|elektrizit|petroleum|oil( &| and)? gas|"
                r"refinery|chemical|chemie|nuclear|solar|wind (power|energy)|"
                r"electric power)\b|전력|에너지|화학|정유"),
 ("금융·결제", r"\b(bank|banca|banco|banque|sparkasse|volksbank|privatbank|"
              r"insurance|versicherung|assurance|seguros|capital management|"
              r"asset management|securities)\b|은행|보험|증권|캐피탈"),
 ("의료·바이오", r"\b(hospital|klinik|clinic|krankenhaus|pharma|pharmaceutic|"
                r"biotech|medical cent|health(care)? (system|group|service)|"
                r"병원|의료원|제약|바이오)\b"),
 ("물류·교통", r"\b(railway|railways|eisenbahn|metro$|subway|transit authority|"
              r"transport(e|es|ation)?$|logistics|shipping|freight|airport|"
              r"port authority)\b|철도|공항|물류|해운|운수"),
 ("건설·부동산", r"\b(construction|bau(unternehmen|gesellschaft)|engineering &|"
                r"real estate|immobilien|properties$)\b|건설|건축|부동산"),
 ("항공·우주·방산", r"\b(airlines?$|airways$|aerospace|aviation|defen[sc]e (systems|"
                  r"industries)|space (agency|center))\b|항공|우주|방위산업"),
 ("숙박·여행", r"\b(hotels?$|resort(s)?$|tourism|tourismus|travel (agency|group)|"
              r"호텔|리조트|관광)\b"),
 ("식품·음료", r"\b(brewery|brauerei|brewing|distillery|winery|weingut|"
              r"coffee (roast|company)|dairy|molkerei)\b|양조|주류|식품"),
]

def pick(b):
    t = " ".join(x for x in (b.get("name_en"), b.get("name_ko")) if x).lower()
    t = NOISE.sub(" ", t)
    for cat, pat in RULES:
        if re.search(pat, t, re.I):
            return cat
    return None

def main():
    apply_ = "--apply" in sys.argv
    p = "_clients/brands.json"
    doc = json.load(open(p))
    n = 0
    from collections import Counter
    hits = Counter(); samples = {}
    for b in doc["brands"]:
        if b.get("category") != "기타": continue
        c = pick(b)
        if not c: continue
        hits[c] += 1
        samples.setdefault(c, []).append(b.get("name_en") or b.get("name_ko"))
        if apply_:
            b["category"] = c
            b["category_src"] = "rule-v1"
        n += 1
    for c, k in hits.most_common():
        print(f"  {c:<14} {k:>5}건   예: {', '.join(str(x)[:22] for x in samples[c][:3])}")
    print(f"\n  총 {n}건 / 기타 {sum(1 for b in doc['brands'] if b.get('category')=='기타')}")
    if apply_:
        json.dump(doc, open(p, "w"), ensure_ascii=False, separators=(",", ":"))
        print("  ✅ 적용")
    else:
        print("  (--apply 없으면 반영 안 함)")

main()
