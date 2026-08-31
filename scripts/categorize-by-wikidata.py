#!/usr/bin/env python3
"""위키데이터 P31(instance of)/P452(industry) 로 '기타' 브랜드를 분류한다.

이름 규칙으로는 8,371개 중 371개(4%)밖에 못 잡았다. 'Melitta'·'Tefal'
같은 이름에는 업종 신호가 아예 없기 때문이다. 그런데 그중 8,090개에
위키데이터 QID 가 있다 — 위키미디어에서 수집한 것들이라 당연하다.

P31 은 사람이 붙인 분류라 이름 추측보다 훨씬 정확하다.

⚠️ SPARQL 은 반드시 POST 로 보낸다. GET 은 120개만 넘어도 URL 길이
   제한에 걸려 실패한다(과거에 겪음).

  python3 scripts/categorize-by-wikidata.py --fetch    # P31 수집 → 캐시
  python3 scripts/categorize-by-wikidata.py            # 매핑 미리보기
  python3 scripts/categorize-by-wikidata.py --apply
"""
import json, os, re, sys, time, urllib.request, urllib.parse
from collections import Counter

CACHE = "_clients/_wikidata-p31.json"
DESC  = "_clients/_wikidata-desc.json"
EP = "https://query.wikidata.org/sparql"
UA = "semologo-categorizer/1.0 (https://semologo.com; vibers.leo@gmail.com)"

def sparql(qids):
    vals = " ".join(f"wd:{q}" for q in qids)
    q = f"""SELECT ?item ?t ?ind WHERE {{
      VALUES ?item {{ {vals} }}
      OPTIONAL {{ ?item wdt:P31 ?t }}
      OPTIONAL {{ ?item wdt:P452 ?ind }}
    }}"""
    data = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
    req = urllib.request.Request(EP, data=data,
        headers={"User-Agent": UA, "Accept": "application/sparql-results+json",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["results"]["bindings"]

def fetch():
    d = json.load(open("_clients/brands.json"))["brands"]
    qids = sorted({b["wikidata"] for b in d
                   if b.get("category") == "기타" and b.get("wikidata")})
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = [q for q in qids if q not in cache]
    print(f"  QID {len(qids)} · 캐시 {len(cache)} · 받을 것 {len(todo)}")
    B = 300
    for i in range(0, len(todo), B):
        chunk = todo[i:i+B]
        for attempt in range(3):
            try:
                rows = sparql(chunk); break
            except Exception as e:
                print(f"   재시도 {attempt+1}: {type(e).__name__}"); time.sleep(8)
        else:
            print("   ⛔ 3회 실패 — 중단"); break
        for q in chunk: cache.setdefault(q, {"t": [], "ind": []})
        for r in rows:
            q = r["item"]["value"].rsplit("/", 1)[-1]
            for k, f in (("t", "t"), ("ind", "ind")):
                if f in r:
                    v = r[f]["value"].rsplit("/", 1)[-1]
                    if v not in cache[q][k]: cache[q][k].append(v)
        json.dump(cache, open(CACHE, "w"))
        print(f"   {min(i+B,len(todo))}/{len(todo)}", flush=True)
        time.sleep(1.5)
    print(f"  ✅ 캐시 {len(cache)}건")

# P31/P452 QID → 우리 카테고리.
#
# ⚠️ QID 를 추측해서 적으면 안 된다. 처음에 그렇게 했다가 존재하지 않는
#    'Q4830453f' 같은 값을 넣어 Avon(화장품)이 공공기관이 되는 오분류가 났다.
#    아래는 전부 실제 레이블을 조회해 확인한 것이다.
#
# 'business'(Q4830453)·'enterprise'·'public company' 는 3,500건이 넘지만
# 업종 신호가 아니라 법인격이라 **일부러 뺐다.** 그런 것들은 P452(업종)나
# 위키데이터 설명문으로 넘긴다.
MAP = {
 "국가·지역": ["Q484170","Q515","Q3957","Q532"],
 "공공·기관": ["Q11795382","Q18744396","Q37002670","Q270791","Q484652",
            "Q1968122","Q7210356","Q60589804","Q48204","Q130370871","Q112166113",
            "Q3624078","Q7275","Q43229","Q327333","Q15911314","Q192350","Q35509"],
 "미디어·엔터": ["Q1331793","Q11033","Q104213567","Q618779","Q21473229","Q4373046",
              "Q14350","Q1616075","Q15265344","Q1002697","Q11032"],
 "스포츠": ["Q18608583","Q17156793","Q13393265","Q27020041","Q1318941","Q2338524",
          "Q353027","Q476028","Q847017","Q13406554","Q625994"],
 "물류·교통": ["Q1358919","Q178512","Q155930","Q49845","Q17018236","Q291240",
            "Q740752","Q1786828","Q249556"],
 "에너지·화학": ["Q1951366","Q383973","Q1326885","Q180388","Q44497","Q1924906",
              "Q2283886","Q134447"],
 "금융·결제": ["Q4290","Q14864997","Q22687","Q806718","Q2088357","Q680206"],
 "식품·음료": ["Q11707","Q4899370","Q11451","Q131734"],
 "IT·테크": ["Q19967801","Q7094076","Q11016","Q7397"],
 "제조·그룹": ["Q55190325","Q56604188","Q117156504","Q83405"],
 "유통·쇼핑": ["Q220695","Q161439","Q41767","Q507619","Q4304101","Q11315"],
 "의료·바이오": ["Q130370967","Q16917","Q4287745","Q19599563","Q11173"],
 "교육": ["Q86732061","Q3918","Q875538","Q3914","Q9826","Q189004"],
 "건설·부동산": ["Q11303","Q1341478"],
 "항공·우주·방산": ["Q18201623","Q46970","Q936518"],
 "숙박·여행": ["Q27686","Q875157"],
 "자동차": ["Q786820"],
}

# 위키데이터 영문 설명문에 쓰는 규칙. P31 이 'business' 뿐인 3,500건을
# 여기서 건진다 — "German coffee company" 처럼 설명문에는 업종이 들어 있다.
DESC_RULES = [
 # ⚠️ 도시를 공공·기관에 넣으면 안 된다. Menlo Park(도시)가 정부조직 옆에
 #    서게 된다. 이 서비스에서 도시는 '국가·지역'(국기·문장)과 같은 성격이다.
 ("국가·지역", r"\b(city in |town in |municipality in |commune in |village in |"
            r"capital (city )?of|(prefecture|province|state|region|county) (in|of) )"),
 ("금융·결제", r"\b(bank|banking|insurance|insurer|financial servic|asset manage|"
             r"investment (bank|firm|manage)|credit union|payment|fintech)\b"),
 ("의료·바이오", r"\b(pharmaceutic|biotech|hospital|healthcare|health care|"
              r"medical (device|technolog|centre|center)|clinic)\b"),
 ("공공·기관", r"\b(government agency|ministry|municipalit|commune|"
            r"public authority|regulatory|state agency|"
            r"political party|trade union|non-?profit organi[sz]ation|"
            r"international organi[sz]ation|embassy)\b"),
 ("교육", r"\b(universit|college|school|educational institution|research institute|"
        r"academy)\b"),
 ("미디어·엔터", r"\b(television (channel|network|station)|radio (station|network)|"
              r"newspaper|magazine|publisher|publishing|record label|film studio|"
              r"media (company|group|conglomerate)|broadcaster|news agency)\b"),
 ("스포츠", r"\b(football club|sports? (club|team|league|season|event)|"
          r"basketball (club|team)|baseball (club|team)|olympic|championship)\b"),
 ("물류·교통", r"\b(airline|railway|railroad|transport(ation)? company|logistics|"
            r"shipping (company|line)|bus (operator|company)|metro system|"
            r"public transport)\b"),
 ("에너지·화학", r"\b(energy company|electric utility|utility company|oil (and|&) gas|"
              r"petroleum|chemical (company|manufactur)|mining company|"
              r"power (company|plant|utility))\b"),
 ("식품·음료", r"\b(brewery|brewing company|winery|distillery|food (company|"
            r"manufactur|producer|processing)|beverage|dairy|restaurant chain|"
            r"coffee (company|roaster)|confectioner)\b"),
 ("자동차", r"\b(automotive|car manufactur|automobile manufactur|motorcycle "
          r"manufactur|auto parts|tire manufactur)\b"),
 ("유통·쇼핑", r"\b(retail(er|ing)? (chain|company|group)?|supermarket|"
            r"department store|e-commerce|online (shop|store|retail)|"
            r"fashion (retail|brand)|watchmak|jewell?er)\b"),
 ("IT·테크", r"\b(software (company|developer)|technology company|it (company|"
           r"servic)|semiconductor|computer (hardware|manufactur)|"
           r"internet company|web servic|cloud (computing|servic))\b"),
 ("게임", r"\b(video game (developer|publisher|company)|game studio)\b"),
 ("건설·부동산", r"\b(construction (company|firm)|real estate|property develop|"
              r"engineering (company|firm)|architecture firm|skyscraper|building in)\b"),
 ("항공·우주·방산", r"\b(aerospace|defen[sc]e (contractor|company)|"
                r"aircraft manufactur|space agency)\b"),
 ("숙박·여행", r"\b(hotel (chain|group|company)|resort|travel (company|agency)|"
            r"tour operator|tourism)\b"),
 ("통신", r"\b(telecommunications?|telecom (company|operator)|mobile network "
        r"operator|internet service provider)\b"),
 ("제조·그룹", r"\b(manufactur(er|ing) (company|conglomerate)?|industrial "
            r"(company|conglomerate|group)|machinery|steel (producer|company)|"
            r"textile)\b"),
 ("뷰티·패션", r"\b(cosmetics|clothing (brand|company|manufactur)|"
            r"fashion (house|label|brand)|footwear|luxury (brand|goods)|perfum)\b"),
 ("교육", r"\b(publisher of (textbook|educational))\b"),
]

LOOK = {}
for cat, qs in MAP.items():
    for q in qs: LOOK.setdefault(q, cat)

def main():
    if "--fetch" in sys.argv: return fetch()
    if not os.path.exists(CACHE):
        print("  캐시 없음 — 먼저 --fetch"); return
    cache = json.load(open(CACHE))
    desc = {}
    if os.path.exists(DESC): desc = json.load(open(DESC))
    doc = json.load(open("_clients/brands.json"))
    hits = Counter(); by_src = Counter(); samples = {}
    left_desc = Counter()
    n = 0
    for b in doc["brands"]:
        if b.get("category") != "기타": continue
        q = b.get("wikidata") or ""
        c = cache.get(q)
        cat = src = None
        if c:
            # P452(업종)를 P31 보다 먼저 본다 — 업종이 훨씬 구체적이다
            for x in c["ind"] + c["t"]:
                if x in LOOK: cat, src = LOOK[x], "p31"; break
        if not cat and desc.get(q):
            dl = desc[q].lower()
            for cc, pat in DESC_RULES:
                if re.search(pat, dl, re.I): cat, src = cc, "desc"; break
            if not cat: left_desc[desc[q][:48]] += 1
        if not cat: continue
        hits[cat] += 1; by_src[src] += 1
        samples.setdefault(cat, []).append(
            f"{b.get('name_en') or b.get('name_ko')}")
        n += 1
        if "--apply" in sys.argv:
            b["category"] = cat; b["category_src"] = "wikidata-" + src
    for c, k in hits.most_common():
        print(f"  {c:<14} {k:>5}건   예: {', '.join(str(x)[:20] for x in samples[c][:3])}")
    print(f"\n  분류 {n}건 (P31/업종 {by_src['p31']} · 설명문 {by_src['desc']})")
    print(f"  남은 기타 {sum(1 for b in doc['brands'] if b.get('category')=='기타') - (n if '--apply' not in sys.argv else 0)}")
    if "--sample-left" in sys.argv:
        print("\n  못 잡은 설명문 상위 30:")
        for d, k in left_desc.most_common(30): print(f"     {k:>4}  {d}")
    if "--apply" in sys.argv:
        json.dump(doc, open("_clients/brands.json", "w"),
                  ensure_ascii=False, separators=(",", ":"))
        print("  ✅ 적용")

main()
