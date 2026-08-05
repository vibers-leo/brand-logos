#!/usr/bin/env python3
"""
정부·공공기관 로고 수집 — Wikimedia Commons SVG
CF Worker 프록시(wikimedia-proxy.yahwaedge.workers.dev)를 통해 IP rate limit 우회
"""

import json
import os
import hashlib
import subprocess
import time
import urllib.parse

BRANDS_JSON = os.path.join(os.path.dirname(__file__), "../_clients/brands.json")
CLIENTS_DIR = os.path.join(os.path.dirname(__file__), "../_clients")
WIKIMEDIA_PROXY = "https://wikimedia-proxy.yahwaedge.workers.dev"

# (id, 한글명, 영문명, commons_filename)
TARGETS = [
    # 한국 정부부처
    ("kr-moef", "기획재정부", "Ministry of Economy and Finance (Korea)", "File:Ministry of Economy and Finance of the Republic of Korea Logo (horizontal).svg"),
    ("kr-moe", "교육부", "Ministry of Education (Korea)", "File:Emblem of the Ministry of Education (South Korea) (English).svg"),
    ("kr-msit", "과학기술정보통신부", "Ministry of Science and ICT (Korea)", "File:Ministry of Science and ICT of the Republic of Korea Logo (horizontal).svg"),
    ("kr-mofa", "외교부", "Ministry of Foreign Affairs (Korea)", "File:Ministry of Foreign Affairs of the Republic of Korea Logo (horizontal).svg"),
    ("kr-moj", "법무부", "Ministry of Justice (Korea)", "File:Ministry of Justice of the Republic of Korea Logo (horizontal).svg"),
    ("kr-mod", "국방부", "Ministry of National Defense (Korea)", "File:Emblem of the Ministry of National Defense (South Korea).svg"),
    ("kr-mois", "행정안전부", "Ministry of the Interior and Safety (Korea)", "File:Ministry of the Interior and Safety of the Republic of Korea Logo (horizontal).svg"),
    ("kr-mafra", "농림축산식품부", "Ministry of Agriculture, Food and Rural Affairs (Korea)", "File:Ministry of Agriculture, Food and Rural Affairs of the Republic of Korea Logo (horizontal).svg"),
    ("kr-motie", "산업통상자원부", "Ministry of Trade, Industry and Energy (Korea)", "File:Ministry of Trade, Industry and Energy of the Republic of Korea Logo (horizontal).svg"),
    ("kr-mohw", "보건복지부", "Ministry of Health and Welfare (Korea)", "File:Ministry of Health and Welfare of the Republic of Korea Logo (horizontal).svg"),
    ("kr-me", "환경부", "Ministry of Environment (Korea)", "File:Ministry of Environment of the Republic of Korea Logo (English) (horizontal).svg"),
    ("kr-moel", "고용노동부", "Ministry of Employment and Labor (Korea)", "File:Ministry of Employment and Labor of the Republic of Korea Logo (horizontal).svg"),
    ("kr-mogef", "여성가족부", "Ministry of Gender Equality and Family (Korea)", "File:Ministry of Gender Equality and Family of the Republic of Korea Logo (horizontal).svg"),
    ("kr-molit", "국토교통부", "Ministry of Land, Infrastructure and Transport (Korea)", "File:Ministry of Land, Infrastructure and Transport of the Republic of Korea Logo (English) (horizontal).svg"),
    ("kr-mof", "해양수산부", "Ministry of Oceans and Fisheries (Korea)", "File:Ministry of Oceans and Fisheries of the Republic of Korea Logo (horizontal).svg"),
    ("kr-smba", "중소벤처기업부", "Ministry of SMEs and Startups (Korea)", "File:Ministry of SMEs and Startups of the Republic of Korea Logo (horizontal).svg"),
    ("kr-mofu", "통일부", "Ministry of Unification (Korea)", "File:Ministry of Unification of the Republic of Korea Logo (horizontal).svg"),
    # 한국 공공기관
    ("kr-nts", "국세청", "National Tax Service Korea", "File:National Tax Service of the Republic of Korea Logo (horizontal).svg"),
    ("kr-customs", "관세청", "Korea Customs Service", "File:Korea Customs Service Logo (horizontal).svg"),
    ("kr-npa", "경찰청", "Korean National Police Agency", "File:Emblem of the Korean National Police Agency.svg"),
    ("kr-spo", "검찰청", "Prosecution Service of Korea", "File:Emblem of the Prosecution Service of Korea.svg"),
    ("kr-kftc", "공정거래위원회", "Korea Fair Trade Commission", "File:Emblem of the Korea Fair Trade Commission (South Korea) (English) (horizontal).svg"),
    ("kr-fsc", "금융위원회", "Financial Services Commission (Korea)", "File:Emblem of the Financial Services Commission (English) (horizontal).svg"),
    ("kr-kepco", "한국전력공사", "KEPCO", "File:Korea-Electric-Power-Corporation-Logo.svg"),
    ("kr-korail", "코레일", "Korail", "File:Korail logo.svg"),
    # 한국 광역시·도
    ("kr-incheon", "인천광역시", "Incheon Metropolitan City", "File:Emblem of Incheon.svg"),
    ("kr-busan", "부산광역시", "Busan Metropolitan City", "File:Symbol of Busan (2023–).svg"),
    ("kr-gyeonggi", "경기도", "Gyeonggi Province", "File:Emblem of Gyeonggi Province (2021).svg"),
    # 국제기구
    ("un", "유엔", "United Nations", "File:UN emblem blue.svg"),
    ("who", "세계보건기구", "World Health Organization", "File:WHO logo.svg"),
    ("unesco", "유네스코", "UNESCO", "File:UNESCO logo.svg"),
    ("unicef", "유니세프", "UNICEF", "File:Logo of UNICEF.svg"),
    ("wto", "세계무역기구", "World Trade Organization", "File:World Trade Organization (logo and wordmark).svg"),
    ("world-bank", "세계은행", "World Bank", "File:World_Bank_logo.svg"),
    ("icc", "국제형사재판소", "International Criminal Court", "File:International Criminal Court logo.svg"),
    ("iaea", "국제원자력기구", "International Atomic Energy Agency", "File:International Atomic Energy Agency Logo.svg"),
    ("icrc", "국제적십자위원회", "International Committee of the Red Cross", "File:International Committee of the Red Cross emblem.svg"),
    ("unhcr", "유엔난민기구", "UNHCR", "File:UNHCR logo only (cropped).svg"),
    ("wipo", "세계지식재산기구", "WIPO", "File:WIPO Logo.svg"),
    ("opec", "석유수출국기구", "OPEC", "File:OPEC Logo.svg"),
    ("nato", "나토", "NATO", "File:Flag of NATO.svg"),
    ("eu", "유럽연합", "European Union", "File:Flag of Europe.svg"),
    # 미국 연방기관
    ("us-nasa", "나사", "NASA", "File:NASA logo.svg"),
    ("us-fbi", "FBI", "Federal Bureau of Investigation", "File:Today's FBI logo.svg"),
    ("us-cia", "CIA", "Central Intelligence Agency", "File:Seal of the Central Intelligence Agency.svg"),
    ("us-nsa", "NSA", "National Security Agency", "File:Logo of the National Security Agency and Central Security Service.svg"),
    ("us-dod", "미국 국방부", "United States Department of Defense", "File:Seal of the United States Department of Defense.svg"),
    ("us-state", "미국 국무부", "United States Department of State", "File:Seal of the United States Department of State.svg"),
    ("us-fda", "미국 식품의약국", "U.S. Food and Drug Administration", "File:Logo of the United States Food and Drug Administration.svg"),
    ("us-cdc", "미국 질병통제예방센터", "Centers for Disease Control and Prevention", "File:US CDC logo.svg"),
    ("us-epa", "미국 환경보호청", "United States Environmental Protection Agency", "File:Seal of the United States Environmental Protection Agency.svg"),
    ("us-irs", "미국 국세청", "Internal Revenue Service", "File:Internal Revenue Service logo.svg"),
    # 해외 주요 정부기관
    ("uk-nhs", "영국 국가보건서비스", "National Health Service (UK)", "File:National Health Service (England) logo.svg"),
    ("de-bundestag", "독일 연방의회", "Bundestag", "File:Deutscher Bundestag logo.svg"),
    ("jp-mofa", "일본 외무성", "Ministry of Foreign Affairs of Japan", "File:Seal of the Ministry of Foreign Affairs of Japan.svg"),
    ("fr-gov", "프랑스 정부", "Government of France", "File:Logo - République française.svg"),
    ("ca-gov", "캐나다 정부", "Government of Canada", "File:Canada wordmark.svg"),
]

def commons_file_to_url(filename):
    """Wikimedia Commons File: 이름 → 직접 다운로드 URL (MD5 기반)"""
    name = filename.replace("File:", "").replace(" ", "_")
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    encoded = urllib.parse.quote(name, safe="")
    return f"https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[0:2]}/{encoded}"

def fetch_via_proxy(wikimedia_url, timeout=30):
    """CF Worker 프록시를 통해 다운로드"""
    proxy_url = f"{WIKIMEDIA_PROXY}?url={urllib.parse.quote(wikimedia_url, safe='')}"
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), proxy_url],
            capture_output=True, timeout=timeout + 10
        )
        if result.returncode == 0 and result.stdout and len(result.stdout) > 100:
            content = result.stdout
            # SVG 또는 이미지 데이터인지 확인
            if b"<svg" in content or b"<?xml" in content or content[:4] in (b"\x89PNG", b"GIF8", b"\xff\xd8\xff"):
                return content
    except Exception as e:
        print(f"    프록시 오류: {e}")
    return None

def load_brands():
    with open(BRANDS_JSON, encoding="utf-8") as f:
        return json.load(f)

def save_brands(data):
    with open(BRANDS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def brand_exists(brands, brand_id):
    return any(b["id"] == brand_id for b in brands)

def main():
    data = load_brands()
    brands = data["brands"] if "brands" in data else data

    added = 0
    skipped = 0
    failed = []

    for (brand_id, name_ko, name_en, commons_file) in TARGETS:
        if brand_exists(brands, brand_id):
            print(f"  [{brand_id}] 이미 존재 — 스킵")
            skipped += 1
            continue

        svg_url = commons_file_to_url(commons_file)
        print(f"  [{brand_id}] {name_ko} 다운로드 중...", end=" ", flush=True)

        content = fetch_via_proxy(svg_url)

        if content:
            brand_dir = os.path.join(CLIENTS_DIR, brand_id)
            os.makedirs(brand_dir, exist_ok=True)

            svg_path = os.path.join(brand_dir, "logo.svg")
            with open(svg_path, "wb") as f:
                f.write(content)

            brands.append({
                "id": brand_id,
                "name_ko": name_ko,
                "name_en": name_en,
                "category": "공공·기관",
                "has_svg": True,
                "has_png": False,
                "source": "wikimedia-commons"
            })
            print(f"✅ ({len(content):,}B)")
            added += 1
        else:
            print(f"❌ 실패")
            failed.append((brand_id, name_ko, svg_url))

        time.sleep(0.5)

    if "brands" in data:
        data["brands"] = brands
    save_brands(data)

    print(f"\n완료: {added}개 추가, {skipped}개 스킵, {len(failed)}개 실패")
    if failed:
        print("\n실패 목록:")
        for fid, fname, furl in failed:
            print(f"  {fid} ({fname}): {furl}")

if __name__ == "__main__":
    main()
