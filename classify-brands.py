#!/usr/bin/env python3
"""brands.json 카테고리 + name_ko 자동 분류"""

import json, re

RULES = [
    # (category, [id/name 키워드 리스트])
    ("게임",          ["ncsoft","nexon","krafton","netmarble","smilegate","gamerating",
                       "devsisters","rebellions","ncg","game-rating"]),
    ("엔터테인먼트",   ["hybe","sm-entertainment","sm-culture","jyp","yg-entertainment",
                       "yg-plus","big-hit","big-planet","bh-entertainment","konnect",
                       "star-news","sidushq","iok-company","attrakt","blockberry",
                       "dear-u","dearu","abu-record","abd-record","emi-music","dc-media",
                       "4dx","screenx","cgv","iconix","bubble"]),
    ("전자/IT",       ["samsung","lg-elec","lg-chem","lg-energy","lg-gram",
                       "sk-hynix","hynix","kt-","kt ",
                       "naver","kakao","nhn","daum","coupang","gmarket","upbit",
                       "sentbe","lendit","bizpass","superplace","upstage","pantech",
                       "iriver","mpio","astellkern","bixolon","bioneer","sandoll",
                       "creatip","giolite","dawonsys","dnalink","inqtenlogo",
                       "korea-data-systems","ktg","kth","ktf","kt-tech","kt-skylife",
                       "ktds","ebcard","ahnlab"]),
    ("자동차",        ["hyundai-motor","hyundai-glovis","hyundai-transys","hyundai-wia",
                       "hyundai-rotem","kia","asia-motors","renault-korea","ssangyong",
                       "tata-daewoo","hl-mando","mando","hankook-tire","hankook",
                       "kumho-tire","snt-dynamics","snt-motiv","dn-solutions",
                       "hyundai-mobis","hyundai-commercial","daewoo-motors",
                       "kg-mobility"]),
    ("건설/부동산",   ["hyundai-engineering","hyundai-development","hdc","daelim",
                       "dl","dongah-const","booyoung","heerim","lx","iljin","dongbu",
                       "ssrst","woojin","woongjin","sampoong","chungcheongnam",
                       "cs-wind","guju","keopyung"]),
    ("철강/중공업",   ["posco","hyundai-heavy","hyundai-steel","hyundai-samho","hmm",
                       "hd-hyundai","seah","korea-zinc","doosan","oci","taekwang",
                       "ls-cable","ls-mtron","lx","dn-solutions","korea-aerospace",
                       "hanwha-aerospace","hanwha-ocean","hanwha-vision","hanwha-solutions"]),
    ("에너지/화학",   ["sk-energy","gs-caltex","s-oil","kepco","kogas","kepco-ec",
                       "kepco-kps","qcells","lg-chem","lg-energy","posco-chemical",
                       "kumho-petrochemical","kumho-polychem","samnam-petrochemical",
                       "hanwha-solutions","hyundai-oilbank","hd-hyundai-oilbank",
                       "korea-electric","kixx"]),
    ("금융/보험",     ["kb","shinhan","hana-bank","hana-financial","nh-investment",
                       "kbank","kakaobank","meritz","kyobo","mirae-asset",
                       "hyundai-capital","hyundai-insurance","hyundai-marine",
                       "industrial-bank","bc-card","db-insurance","db ",
                       "nacf","nffc","suhyup","upbit","lig","mkiscore"]),
    ("통신",          ["kt-","sk-telecom","lg-uplus","olleh","pantech","kt-skylife",
                       "ktf","kt-tech","nate-communications"]),
    ("식품/음료",     ["nongshim","binggrae","lotte-chilsung","lotte-wellfood",
                       "samyang-foods","haitai","orion-corporation","paris-baguette",
                       "dongwon","ottogi","lotte-value","samlip"]),
    ("유통/쇼핑",    ["emart","lotte-mart","lotte-duty","shinsegae","olive-young",
                       "cu-bi","gs25","galleria","gmarket","cu ","emart-24",
                       "paris-baguette"]),
    ("뷰티/패션",     ["isa-knox","amore","lg-household","olive-young","loma","misto",
                       "monami","pro-specs"]),
    ("제약/의료",     ["celltrion","hanmi-pharm","bukwang-pharmaceutical","yuhan",
                       "dong-wha","samyang-biopharm","korea-ginseng","jw-","chunghwa",
                       "national-medical"]),
    ("물류/교통",     ["hanjin","hanjin-shipping","kumho-asiana","korail","smrt",
                       "seoul-metro","sr-corporation","srt","g-bus","neotrans",
                       "daewon-express","daewon-passenger","new-seoul-railroad",
                       "korea-airports","incheon-airport","woojin"]),
    ("미디어/광고",   ["cheil-worldwide","hs-ad","kobaco","cj-enm","dc-inside",
                       "star-news","gallup","leehan","creatip","sandoll",
                       "korea-broadcasting","nate","daum-communications"]),
    ("제조/그룹",     ["samsung-ct","samsung-sds","samsung-bespoke","samsung-mobile",
                       "hanwha","gs ","lotte ","sk ","lg ","cj ","doosan","hyundai ",
                       "hd ","hanssem","tongyang","samyang-corporation","samyang-holdings",
                       "samyang-kasei","samyang-packaging","samyang-ncchem",
                       "kumho-asiana","hyosung","isu","seah","hanbo","ls ","lx ",
                       "dongah","hyundai-lc","hansol"]),
    ("스타트업/핀테크",["sentbe","lendit","bizpass","superplace","upstage","rebellions",
                        "giolite","leehan","dnalink","inqtenlogo","dawonsys"]),
    ("공공/기관",     ["korean-red-cross","korea-tourism","korea-sports","korean-olympic",
                       "korea-internet","korea-media-rating","game-rating",
                       "korea-digital-design","kobaco-1997","k-startup","kisa",
                       "komsco","kintex","defense-agency","korea-baseball",
                       "korea-exchance","korea-exchange","kta","gallup-korea",
                       "chungcheongnam","coex"]),
    ("완구/라이프스타일",["nintendo","artbox","monami","pro-specs","samchuly"]),
    ("반려동물",      ["royal-canin"]),
    ("금속/소재",     ["posco","korea-zinc","seah","ls-cable","hyundai-steel",
                       "oci","taekwang","samyang-ncchem","kumho-polychem",
                       "kumho-petrochemical","samnam-petrochemical"]),
]

# name_ko 매핑 (누락된 15개)
NAME_KO_MAP = {
    "logo-daewoo-electronics-south-korea": "대우전자",
    "logo-hankook-tire-2025": "한국타이어",
    "logo-hanon": "한온시스템",
    "logo-lg-lifes-good-1995-2014": "LG전자 (구 로고)",
    "logo-lg-gram": "LG 그램",
    "logo-of-kakao-m": "카카오M",
    "logo-of-komsco": "한국조폐공사",
    "logo-of-nhn-corporation-2024": "NHN",
    "logo-of-seoul-line9-operation": "서울9호선운영",
    "logo-wordmark-daewoo-electronics-now-winia-electronics": "위니아전자 (구 대우전자)",
    "logo-wordmark-daewoo-motors-2002-2016": "대우자동차 (구 로고)",
    "logo-wordmark-winia-electronics-before-daewoo-electronics": "위니아전자",
    "logo-newsindoh": "뉴스인도",
    "logo-qr": "QR 코드",
    "logo-of-the-lg-corporation-1995-2014": "LG (구 럭키금성 로고)",
}

def classify(brand_id: str, name: str) -> str:
    key = (brand_id + " " + name).lower()
    for category, keywords in RULES:
        for kw in keywords:
            if kw.lower() in key:
                return category
    return "기업"

def main():
    with open("_clients/brands.json", encoding="utf-8") as f:
        raw = json.load(f)
    brands = raw["brands"]

    changed = 0
    ko_added = 0
    cat_counts = {}

    for b in brands:
        bid = b.get("id", "")
        name = b.get("name", "")

        # name_ko 보충
        if not b.get("name_ko") and bid in NAME_KO_MAP:
            b["name_ko"] = NAME_KO_MAP[bid]
            ko_added += 1

        # category 재분류 (기업인 것만)
        if b.get("category") == "기업":
            new_cat = classify(bid, name)
            if new_cat != "기업":
                b["category"] = new_cat
                changed += 1

        cat = b.get("category", "미분류")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    raw["brands"] = brands
    with open("_clients/brands.json", "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    print(f"카테고리 변경: {changed}개")
    print(f"name_ko 추가: {ko_added}개")
    print("\n카테고리 분포:")
    for k, v in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}개")

if __name__ == "__main__":
    main()
