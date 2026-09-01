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

# 위키데이터 영문 설명문에 쓰는 규칙. P31 이 'business' 뿐인 수천 건을
# 여기서 건진다 — "German coffee company" 처럼 설명문에는 업종이 들어 있다.
#
# ⚠️⚠️ **어근에는 뒤쪽 \b 를 붙이면 안 된다.** 이 함정을 하루에 세 번 밟았다:
#     `financial technolog\b`  → 'financial technology' 미매칭 (뒤에 y)
#     `\bpharmaceutic\b`       → 'pharmaceutical company' 미매칭 (뒤에 al)
#     `manufactur(er|ing) `    → 'manufacturer of X' 미매칭 (뒤에 of)
#   에러가 안 나고 조용히 매칭만 실패하므로 눈치채기 어렵다.
#   어근은 `\w*` 로 열어 두고, 완전한 단어에만 \b 를 쓴다.
#   하이픈 표기도 함께 받는다 — 'real-estate company' 가 통째로 샜다.
DESC_RULES = [
 ("국가·지역", r"^(city|town|municipality|commune|village|borough|district)"
            r"( and (city|town|municipality|commune|village))? (in|of) |"
            r"^capital (city )?of|^(prefecture|province|state|county) (in|of) |"
            r"^canton of |^(region|county|province|state) of |"
            r"^(federal |autonomous )?(state|region|territory) in "),

 ("금융·결제", r"\b(bank|banks|banking|insurance|insurer|reinsur\w*|"
             r"financial servic\w*|financial tech\w*|asset manage\w*|"
             r"investment (bank|firm|manage\w*|compan\w*)|credit union|"
             r"payment\w*|fintech|pension fund|hedge fund|private equity|"
             r"stock exchange|securities|brokerage|mortgage|"
             r"venture capital|building society)\b"),

 ("의료·바이오", r"pharmaceutic\w*|biotech\w*|"
              r"\b(hospital|hospitals|healthcare|health care|"
              r"medical (device|technolog\w*|centre|center|equipment)|"
              r"clinic|clinics|dental|diagnostic\w*|vaccine\w*|"
              r"nursing home|health (system|insurance|service))\b"),

 ("공공·기관", r"\b(government agency|ministry|public authority|"
            r"regulatory|state agency|municipal authority|"
            r"political party|trade union|labor union|"
            r"non-?profit organi[sz]ation|charit\w*|foundation|"
            r"international organi[sz]ation|embassy|"
            r"professional (association|body)|trade association|"
            r"advocacy group|think tank|research institute|"
            r"public transit agency|police|fire department|"
            r"national (agency|authority|bureau|library|archives))\b"),

 ("교육", r"universit\w*|"
        r"\b(college|school|schools|educational institution|academy|"
        r"kindergarten|training (centre|center|institute)|"
        r"e-?learning|online course\w*)\b"),

 ("미디어·엔터", r"broadcast\w*|publish\w*|"
              r"\b(television (channel|network|station|series|show|programme|program)|"
              r"tv (channel|network|series|show)|radio (station|network)|"
              r"newspaper|magazine|record label|film studio|"
              r"media (company|group|conglomerate|outlet)|news (agency|website|site|show)|"
              r"streaming (service|platform)|orchestra|"
              r"theat(re|er)|museum|festival|concert|"
              r"animation studio|talent agency|"
              r"comic|manga|anime|podcast|subreddit|"
              r"stock (photo|photos|video|footage)|ticket agent)\b"),

 ("스포츠", r"\b(football club|sports? (club|team|league|season|event|association)|"
          r"basketball (club|team)|baseball (club|team)|"
          r"volleyball|handball|ice hockey|rugby|cricket club|"
          r"olympic|championship|motorsport|racing team|"
          r"golf (club|course)|stadium|arena|fitness (chain|centre|center)|gym)\b"),

 ("물류·교통", r"\b(airline|airlines|railway|railways|railroad|"
            r"transport (company|operator|authority|system)|transportation company|"
            r"logistics|shipping (company|line)|freight|courier|"
            r"bus (operator|company)|metro (system|operator)|"
            r"streetcar|tram|subway|public transport|"
            r"port (authority|operator)|airport|delivery service)\b"),

 ("에너지·화학", r"chemical\w*|petrochemical\w*|"
              r"\b(energy (company|group|supplier)|electric utility|utility company|"
              r"utilities|oil (and|&) gas|oilfield servic\w*|petroleum|refinery|"
              r"mining (company|group)|power (company|plant|utility|producer)|"
              r"electricity (utility|supplier|producer|distribution)|"
              r"(distribution|transmission) network operator|"
              r"renewable energy|solar (company|energy)|wind (power|energy)|"
              r"gas (utility|supplier|station\w*)|coal|natural gas|"
              r"(chain|network) of (gas|petrol|service) stations)\b"),

 ("식품·음료", r"\b(brewery|brewing (company|group)|winery|distillery|"
            r"food (company|manufactur\w*|producer|processing|group|chain)|"
            r"beverage|dairy|soymilk|restaurant (chain|group|company)|"
            r"coffee (company|roaster|chain)|confectioner\w*|"
            r"bakery|snack|soft drink|bottler|catering|"
            r"candy|chocolate|ice cream|meat (processing|producer)|"
            r"seafood|noodle|sauce|spice)\b"),

 ("자동차", r"\b(automotive|car manufactur\w*|automobile manufactur\w*|"
          r"motorcycle manufactur\w*|auto parts|tire manufactur\w*|"
          r"truck manufactur\w*|bus manufactur\w*|car rental|"
          r"vehicle manufactur\w*)\b"),

 ("유통·쇼핑", r"\b(retail\w*|supermarket|hypermarket|department store|"
            r"e-?commerce|online (shop|store|retail\w*|marketplace)|"
            r"convenience store|bookstore|book shop|"
            r"shopping (mall|centre|center)|"
            r"fashion (retail\w*|brand|house|label)|"
            r"watchmak\w*|jewell?er\w*|jewellery|jewelry|"
            r"furniture (retail\w*|store|company)|"
            r"multi-?level marketing|mail order|"
            r"toy (shop|shops|store|company))\b"),

 ("IT·테크", r"softwar\w*|technolog\w*|"
           r"\b(it (company|servic\w*|consult\w*)|semiconductor|"
           r"computer (hardware|manufactur\w*|company)|"
           r"internet (company|servic\w*)|web servic\w*|social network|"
           r"online (platform|servic\w*|community)|"
           r"cloud (computing|servic\w*)|data (centre|center|analytics)|"
           r"operating system|programming language|"
           r"emulator|debugger|api|open-?source|"
           r"artificial intelligence|machine learning|"
           r"cyber ?security|smartphone|smartwatch|tablet computer|laptop|"
           r"group of .{0,20}models produced by)\b"),

 ("게임", r"\b(video game (developer|publisher|company|studio)|"
        r"game (studio|developer|publisher)|"
        r"arcade|esports|gaming (company|platform))\b"),

 ("건설·부동산", r"construct\w*|engineering (company|firm|group)|"
              r"\b(real[- ]estate|property (develop\w*|management|company)|"
              r"architecture firm|architectural|skyscraper|"
              r"building (company|materials)|infrastructure (company|group)|"
              r"cement|housing (association|company))\b"),

 ("항공·우주·방산", r"aerospace|"
                r"\b(defen[sc]e (contractor|company|systems|industr\w*)|"
                r"aircraft manufactur\w*|space (agency|company)|"
                r"satellite (operator|manufactur\w*|servic\w*|communication\w*)|"
                r"missile|armament\w*|weapons manufactur\w*)\b"),

 ("숙박·여행", r"\b(hotel|hotels|resort|resorts|hostel|"
            r"travel (company|agency|group)|tour operator|tourism|"
            r"cruise (line|company)|casino|"
            r"amusement park|theme park|holiday)\b"),

 ("통신", r"telecom\w*|"
        r"\b(mobile network operator|internet (service )?provider|"
        r"isp|broadband|wireless carrier|"
        r"telephone (company|operator)|cable (operator|company))\b"),

 ("제조·그룹", r"manufactur\w*|"
            r"\b(industrial (company|conglomerate|group)|machinery|"
            r"steel (producer|company|mill)|textile\w*|"
            r"paper (mill|company)|packaging|"
            r"electronics (company|manufactur\w*)|electromechanical|"
            r"equipment (manufactur\w*|maker)|"
            r"conglomerate|holding company)\b"),

 ("뷰티·패션", r"cosmetic\w*|fragrance\w*|"
            r"\b(clothing (brand|company|manufactur\w*|retail\w*)|"
            r"fashion (house|label|brand|designer)|footwear|shoe (brand|company)|"
            r"luxury (brand|goods|fashion)|perfum\w*|"
            r"skincare|skin care|makeup|beauty (brand|company)|"
            r"apparel|sportswear|eyewear|handbag)\b"),

 ("반려동물", r"\b(pet (food|care|supplies|products|shop)|veterinar\w*|"
            r"animal (shelter|hospital))\b"),
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
