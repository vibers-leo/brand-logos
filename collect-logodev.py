#!/usr/bin/env python3
"""
logo.dev API 기반 한국 브랜드 로고 수집
- 404 = 로고 없음 (스킵), 200 = 실제 로고
- 무료 1,000req/월 → 한 번에 700개 도메인 처리 가능

사용:
  python3 collect-logodev.py               # 전체 실행
  python3 collect-logodev.py --dry-run     # 다운로드 없이 목록만
  python3 collect-logodev.py --commit      # 완료 후 git commit+push
"""


# 저장 가드 — 확장자와 내용이 다르면 쓰지 않는다 (404 HTML 이 logo.svg 로
# 저장되던 사고 재발 방지). scripts/ 밖에서도 import 되도록 경로를 넣는다.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent / "scripts"))
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from assetguard import safe_write

import argparse, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE       = Path(__file__).parent
LOGO_DIR   = BASE / "_clients"
BRANDS_JSON = LOGO_DIR / "brands.json"
TOKEN      = "pk_PMYAJ8oDRDG9VWZU6uPH6w"
UA         = "VibersLogoDB/1.0 (vibers.leo@gmail.com)"

# ─── 한국 기업 도메인 마스터 리스트 ───────────────────────────────────────
KR_DOMAINS = [
    # ══ IT·플랫폼 ══
    ("kakao.com",           "카카오",           "전자/IT"),
    ("naver.com",           "네이버",           "전자/IT"),
    ("coupang.com",         "쿠팡",             "유통/쇼핑"),
    ("baemin.com",          "배달의민족",       "전자/IT"),
    ("toss.im",             "토스",             "금융/보험"),
    ("karrotmarket.com",    "당근마켓",         "전자/IT"),
    ("musinsa.com",         "무신사",           "유통/쇼핑"),
    ("kurly.com",           "마켓컬리",         "유통/쇼핑"),
    ("oasis.co.kr",         "오아시스",         "유통/쇼핑"),
    ("oliveyoung.co.kr",    "올리브영",         "유통/쇼핑"),
    ("wconcept.co.kr",      "W컨셉",            "유통/쇼핑"),
    ("29cm.co.kr",          "29CM",             "유통/쇼핑"),
    ("ably.kr",             "에이블리",         "유통/쇼핑"),
    ("zigzag.kr",           "지그재그",         "유통/쇼핑"),
    ("brandi.co.kr",        "브랜디",           "유통/쇼핑"),
    ("balaan.co.kr",        "발란",             "유통/쇼핑"),
    ("kream.co.kr",         "크림",             "유통/쇼핑"),
    ("soldout.co.kr",       "솔드아웃",         "유통/쇼핑"),
    ("lotteon.com",         "롯데온",           "유통/쇼핑"),
    ("ssg.com",             "SSG닷컴",          "유통/쇼핑"),
    ("11st.co.kr",          "11번가",           "유통/쇼핑"),
    ("gmarket.co.kr",       "지마켓",           "유통/쇼핑"),
    ("auction.co.kr",       "옥션",             "유통/쇼핑"),
    ("interpark.com",       "인터파크",         "유통/쇼핑"),
    ("tmon.co.kr",          "티몬",             "유통/쇼핑"),
    ("wemakeprice.com",     "위메프",           "유통/쇼핑"),
    ("ns.co.kr",            "NS홈쇼핑",         "유통/쇼핑"),
    ("cjonstyle.com",       "CJ온스타일",       "유통/쇼핑"),
    ("gsshop.com",          "GS샵",             "유통/쇼핑"),
    ("hyundaihmall.com",    "현대H몰",          "유통/쇼핑"),
    ("lotteshopping.com",   "롯데백화점",       "유통/쇼핑"),
    ("shinsegae.com",       "신세계",           "유통/쇼핑"),
    ("galleria.co.kr",      "갤러리아",         "유통/쇼핑"),
    ("thehandsome.com",     "더한섬",           "뷰티/패션"),
    ("kolon.com",           "코오롱",           "제조/그룹"),

    # ══ 금융·보험·핀테크 ══
    ("kbstar.com",          "KB국민은행",       "금융/보험"),
    ("shinhan.com",         "신한은행",         "금융/보험"),
    ("wooribank.com",       "우리은행",         "금융/보험"),
    ("hanabank.com",        "하나은행",         "금융/보험"),
    ("ibk.co.kr",           "IBK기업은행",      "금융/보험"),
    ("nhbank.com",          "NH농협은행",       "금융/보험"),
    ("kbank.co.kr",         "케이뱅크",         "금융/보험"),
    ("kakaobank.com",       "카카오뱅크",       "금융/보험"),
    ("tossbank.com",        "토스뱅크",         "금융/보험"),
    ("kbinsure.co.kr",      "KB손해보험",       "금융/보험"),
    ("samsung.com/sec/insurance", "삼성화재",   "금융/보험"),
    ("samsungfire.com",     "삼성화재",         "금융/보험"),
    ("meritzfire.com",      "메리츠화재",       "금융/보험"),
    ("hyundai-insurance.com","현대해상",        "금융/보험"),
    ("db-fi.com",           "DB손해보험",       "금융/보험"),
    ("lottefinance.co.kr",  "롯데카드",         "금융/보험"),
    ("hyundaicard.com",     "현대카드",         "금융/보험"),
    ("shinhancard.com",     "신한카드",         "금융/보험"),
    ("kbcard.com",          "KB국민카드",       "금융/보험"),
    ("miraeasset.com",      "미래에셋",         "금융/보험"),
    ("samsungsecurities.com","삼성증권",        "금융/보험"),
    ("kiwoom.com",          "키움증권",         "금융/보험"),
    ("nhqv.com",            "NH투자증권",       "금융/보험"),
    ("hi-ib.com",           "하이투자증권",     "금융/보험"),
    ("upbit.com",           "업비트",           "금융/보험"),
    ("bithumb.com",         "빗썸",             "금융/보험"),
    ("coinone.co.kr",       "코인원",           "금융/보험"),
    ("dunamu.com",          "두나무",           "전자/IT"),

    # ══ 통신 ══
    ("kt.com",              "KT",               "통신"),
    ("sktelecom.com",       "SK텔레콤",         "통신"),
    ("lguplus.com",         "LG유플러스",       "통신"),
    ("sk.com",              "SK그룹",           "제조/그룹"),
    ("skbroadband.com",     "SK브로드밴드",     "통신"),
    ("kticloud.com",        "KT클라우드",       "전자/IT"),

    # ══ 전자·반도체·IT제조 ══
    ("samsung.com",         "삼성전자",         "전자/IT"),
    ("lg.com",              "LG전자",           "전자/IT"),
    ("skhynix.com",         "SK하이닉스",       "전자/IT"),
    ("samsung.com/sec",     "삼성SDI",          "전자/IT"),
    ("samsungsdi.com",      "삼성SDI",          "전자/IT"),
    ("lgdisplay.com",       "LG디스플레이",     "전자/IT"),
    ("lgenergy.com",        "LG에너지솔루션",   "전자/IT"),
    ("hanssem.com",         "한샘",             "제조/그룹"),
    ("coway.co.kr",         "코웨이",           "전자/IT"),
    ("winix.com",           "위닉스",           "전자/IT"),
    ("dongbu.com",          "동부대우전자",     "전자/IT"),
    ("winia.com",           "위니아",           "전자/IT"),
    ("lutronic.com",        "루트로닉",         "제약/의료"),
    ("kakaomobility.com",   "카카오모빌리티",   "전자/IT"),
    ("kakaoentertainment.com","카카오엔터",     "엔터테인먼트"),
    ("kakaopage.com",       "카카오페이지",     "전자/IT"),
    ("kakaogames.com",      "카카오게임즈",     "게임"),
    ("naverwebtoon.com",    "네이버웹툰",       "미디어/광고"),
    ("ncloudplatform.com",  "네이버클라우드",   "전자/IT"),
    ("krafton.com",         "크래프톤",         "게임"),
    ("ncsoft.com",          "엔씨소프트",       "게임"),
    ("nexon.com",           "넥슨",             "게임"),
    ("netmarble.com",       "넷마블",           "게임"),
    ("smilegate.com",       "스마일게이트",     "게임"),
    ("devsisters.com",      "데브시스터즈",     "게임"),
    ("pearlabyss.com",      "펄어비스",         "게임"),
    ("com2us.com",          "컴투스",           "게임"),
    ("gamevil.com",         "게임빌",           "게임"),
    ("wemade.com",          "위메이드",         "게임"),
    ("nexon.co.kr",         "넥슨코리아",       "게임"),
    ("neowiz.com",          "네오위즈",         "게임"),
    ("kakao.games",         "카카오게임즈",     "게임"),
    ("bluehole.net",        "블루홀",           "게임"),
    ("xlgames.com",         "엑스엘게임즈",     "게임"),
    ("kakaoent.com",        "카카오엔터",       "엔터테인먼트"),

    # ══ 엔터테인먼트·미디어 ══
    ("hybe.com",            "하이브",           "엔터테인먼트"),
    ("smentertainment.com", "SM엔터테인먼트",   "엔터테인먼트"),
    ("ygfamily.com",        "YG엔터테인먼트",   "엔터테인먼트"),
    ("jype.com",            "JYP엔터테인먼트",  "엔터테인먼트"),
    ("cjenm.com",           "CJ ENM",           "엔터테인먼트"),
    ("tving.com",           "티빙",             "미디어/광고"),
    ("wavve.com",           "웨이브",           "미디어/광고"),
    ("watcha.com",          "왓챠",             "미디어/광고"),
    ("seezn.com",           "시즌",             "미디어/광고"),
    ("laftel.net",          "라프텔",           "미디어/광고"),
    ("kbs.co.kr",           "KBS",              "미디어/광고"),
    ("mbc.co.kr",           "MBC",              "미디어/광고"),
    ("sbs.co.kr",           "SBS",              "미디어/광고"),
    ("jtbc.co.kr",          "JTBC",             "미디어/광고"),
    ("tvn.co.kr",           "tvN",              "미디어/광고"),
    ("ocn.co.kr",           "OCN",              "미디어/광고"),
    ("mnet.com",            "Mnet",             "미디어/광고"),
    ("yonhapnews.co.kr",    "연합뉴스",         "미디어/광고"),
    ("chosun.com",          "조선일보",         "미디어/광고"),
    ("joongang.co.kr",      "중앙일보",         "미디어/광고"),
    ("donga.com",           "동아일보",         "미디어/광고"),
    ("hani.co.kr",          "한겨레",           "미디어/광고"),
    ("hankyung.com",        "한국경제",         "미디어/광고"),
    ("mk.co.kr",            "매일경제",         "미디어/광고"),
    ("etnews.com",          "전자신문",         "미디어/광고"),
    ("zdnet.co.kr",         "ZDNet Korea",      "미디어/광고"),

    # ══ 자동차 ══
    ("hyundai.com",         "현대자동차",       "자동차"),
    ("kia.com",             "기아",             "자동차"),
    ("genesis.com",         "제네시스",         "자동차"),
    ("renaultkorea.com",    "르노코리아",       "자동차"),
    ("kgmobility.com",      "KG모빌리티",       "자동차"),
    ("hankooktire.com",     "한국타이어",       "자동차"),
    ("kumhotire.com",       "금호타이어",       "자동차"),
    ("nexentire.com",       "넥센타이어",       "자동차"),
    ("mando.com",           "만도",             "자동차"),
    ("hyundaimobis.com",    "현대모비스",       "자동차"),
    ("sntmotiv.com",        "SNT모티브",        "자동차"),
    ("hyundaiglovis.com",   "현대글로비스",     "자동차"),
    ("hyundaisteel.com",    "현대제철",         "철강/중공업"),
    ("hmm21.com",           "HMM",              "물류/교통"),

    # ══ 식품·음료·외식 ══
    ("nongshim.com",        "농심",             "식품/음료"),
    ("ottogi.co.kr",        "오뚜기",           "식품/음료"),
    ("samyang.com",         "삼양식품",         "식품/음료"),
    ("haitai.co.kr",        "해태제과",         "식품/음료"),
    ("orion.co.kr",         "오리온",           "식품/음료"),
    ("binggrae.co.kr",      "빙그레",           "식품/음료"),
    ("lottewellfood.com",   "롯데웰푸드",       "식품/음료"),
    ("crown.co.kr",         "크라운제과",       "식품/음료"),
    ("dongwonfnb.com",      "동원F&B",          "식품/음료"),
    ("cj.net",              "CJ제일제당",       "식품/음료"),
    ("cjfoodville.com",     "CJ푸드빌",         "식품/음료"),
    ("parisbaguette.co.kr", "파리바게뜨",       "식품/음료"),
    ("tous-les-jours.co.kr","뚜레쥬르",         "식품/음료"),
    ("starbucks.co.kr",     "스타벅스코리아",   "식품/음료"),
    ("hollys.co.kr",        "할리스",           "식품/음료"),
    ("ediya.com",           "이디야",           "식품/음료"),
    ("coffeebean.co.kr",    "커피빈코리아",     "식품/음료"),
    ("paik.com",            "빽다방",           "식품/음료"),
    ("mega-mgccoffee.com",  "메가커피",         "식품/음료"),
    ("twosomecoffee.com",   "투썸플레이스",     "식품/음료"),
    ("mcdonalds.co.kr",     "맥도날드코리아",   "식품/음료"),
    ("burgerking.co.kr",    "버거킹코리아",     "식품/음료"),
    ("lotteria.com",        "롯데리아",         "식품/음료"),
    ("bbo.co.kr",           "BBQ",              "식품/음료"),
    ("bhc.co.kr",           "BHC치킨",         "식품/음료"),
    ("kyochon.com",         "교촌치킨",         "식품/음료"),
    ("goobne.com",          "굽네치킨",         "식품/음료"),
    ("dominos.co.kr",       "도미노피자",       "식품/음료"),
    ("pizzahut.co.kr",      "피자헛코리아",     "식품/음료"),
    ("gimbap.net",          "바르다김선생",     "식품/음료"),
    ("innisfree.com",       "이니스프리",       "뷰티/패션"),
    ("lotteconfectionery.com","롯데제과",       "식품/음료"),
    ("haioreum.co.kr",      "해표",             "식품/음료"),

    # ══ 뷰티·패션 ══
    ("amorepacific.com",    "아모레퍼시픽",     "뷰티/패션"),
    ("lghousehold.com",     "LG생활건강",       "뷰티/패션"),
    ("laneige.com",         "라네즈",           "뷰티/패션"),
    ("sulwhasoo.com",       "설화수",           "뷰티/패션"),
    ("skii.com",            "SK-II",            "뷰티/패션"),
    ("etudehouse.com",      "에뛰드",           "뷰티/패션"),
    ("missha.com",          "미샤",             "뷰티/패션"),
    ("toofaced.com",        "투페이스드",       "뷰티/패션"),
    ("romand.co.kr",        "롬앤",             "뷰티/패션"),
    ("clio.co.kr",          "클리오",           "뷰티/패션"),
    ("peripera.co.kr",      "페리페라",         "뷰티/패션"),
    ("tirtir.com",          "티르티르",         "뷰티/패션"),
    ("abib.co.kr",          "어비브",           "뷰티/패션"),
    ("cosrx.com",           "코스알엑스",       "뷰티/패션"),
    ("somebymi.com",        "섬바이미",         "뷰티/패션"),
    ("tntnc.co.kr",         "탠탠",             "뷰티/패션"),
    ("samsung.com/global/galaxy","삼성갤럭시",  "전자/IT"),
    ("fila.co.kr",          "휠라코리아",       "뷰티/패션"),
    ("descente.co.kr",      "데상트코리아",     "뷰티/패션"),
    ("nbkorea.com",         "뉴발란스코리아",   "뷰티/패션"),
    ("kolon.co.kr",         "코오롱스포츠",     "뷰티/패션"),
    ("blackyak.com",        "블랙야크",         "뷰티/패션"),
    ("northfacekorea.com",  "노스페이스코리아", "뷰티/패션"),
    ("mlb-korea.com",       "MLB코리아",        "뷰티/패션"),
    ("abercrombie.co.kr",   "아베크롬비코리아", "뷰티/패션"),
    ("handsome.co.kr",      "한섬",             "뷰티/패션"),
    ("sjyc.co.kr",          "신세계인터내셔날", "뷰티/패션"),
    ("ssfshop.com",         "SSF샵",            "뷰티/패션"),

    # ══ 제약·바이오·의료 ══
    ("celltrion.com",       "셀트리온",         "제약/의료"),
    ("hanmipharm.com",      "한미약품",         "제약/의료"),
    ("yuhan.co.kr",         "유한양행",         "제약/의료"),
    ("donga-pharm.com",     "동아제약",         "제약/의료"),
    ("jw.co.kr",            "JW중외제약",       "제약/의료"),
    ("boryung.co.kr",       "보령제약",         "제약/의료"),
    ("ilyang.co.kr",        "일양약품",         "제약/의료"),
    ("ildong.com",          "일동제약",         "제약/의료"),
    ("chong-kun-dang.com",  "종근당",           "제약/의료"),
    ("hugel.co.kr",         "휴젤",             "제약/의료"),
    ("medytox.com",         "메디톡스",         "제약/의료"),
    ("koreacrescentresearch.com","한국콜마",     "제약/의료"),
    ("kolmar.co.kr",        "한국콜마",         "제약/의료"),
    ("cosmax.co.kr",        "코스맥스",         "제약/의료"),
    ("ildongfoodis.co.kr",  "일동후디스",       "식품/음료"),
    ("samsungbioepis.com",  "삼성바이오에피스", "제약/의료"),
    ("samsungbiologics.com","삼성바이올로직스", "제약/의료"),
    ("sk-biopharma.com",    "SK바이오팜",       "제약/의료"),
    ("sk-bioscience.co.kr", "SK바이오사이언스", "제약/의료"),

    # ══ 건설·부동산 ══
    ("hdec.co.kr",          "현대건설",         "건설/부동산"),
    ("daelim.co.kr",        "대림건설",         "건설/부동산"),
    ("gscaltex.com",        "GS건설",           "건설/부동산"),
    ("gsconst.co.kr",       "GS건설",           "건설/부동산"),
    ("samsungcnt.com",      "삼성물산",         "건설/부동산"),
    ("posco-e.com",         "포스코E&C",        "건설/부동산"),
    ("daewooconstruction.com","대우건설",        "건설/부동산"),
    ("skecoplant.com",      "SK에코플랜트",     "건설/부동산"),
    ("hyundaidevelopment.com","HDC현대산업개발", "건설/부동산"),
    ("dlenc.co.kr",         "DL이앤씨",         "건설/부동산"),
    ("taeyoung.com",        "태영건설",         "건설/부동산"),
    ("kolon.co.kr",         "코오롱글로벌",     "건설/부동산"),
    ("kyobo.co.kr",         "교보생명",         "금융/보험"),
    ("kyoborealco.com",     "교보리얼코",       "건설/부동산"),
    ("lh.or.kr",            "LH한국토지주택공사","공공/기관"),
    ("sh.or.kr",            "서울주택도시공사", "공공/기관"),

    # ══ 에너지·화학·철강 ══
    ("posco.com",           "포스코",           "철강/중공업"),
    ("hyundaisteel.com",    "현대제철",         "철강/중공업"),
    ("dongkuk.com",         "동국제강",         "철강/중공업"),
    ("seoahn.com",          "세아제강",         "철강/중공업"),
    ("kepco.co.kr",         "한국전력",         "에너지/화학"),
    ("kogas.or.kr",         "한국가스공사",     "에너지/화학"),
    ("knoc.co.kr",          "한국석유공사",     "에너지/화학"),
    ("s-oil.com",           "에쓰오일",         "에너지/화학"),
    ("gscaltex.com",        "GS칼텍스",         "에너지/화학"),
    ("skenergyplus.co.kr",  "SK에너지",         "에너지/화학"),
    ("lotte-chemical.com",  "롯데케미칼",       "에너지/화학"),
    ("lgchem.com",          "LG화학",           "에너지/화학"),
    ("skchemicals.com",     "SK케미칼",         "에너지/화학"),
    ("hanwhasolutions.com",  "한화솔루션",       "에너지/화학"),
    ("qcells.com",          "한화큐셀",         "에너지/화학"),
    ("oci.co.kr",           "OCI",              "에너지/화학"),
    ("kumhopchem.com",      "금호석유화학",     "에너지/화학"),
    ("lxhausys.com",        "LX하우시스",       "에너지/화학"),

    # ══ 물류·항공·교통 ══
    ("koreanair.com",       "대한항공",         "물류/교통"),
    ("flyasiana.com",       "아시아나항공",     "물류/교통"),
    ("jejuair.net",         "제주항공",         "물류/교통"),
    ("jinair.com",          "진에어",           "물류/교통"),
    ("airbusan.com",        "에어부산",         "물류/교통"),
    ("eastarjet.com",       "이스타항공",       "물류/교통"),
    ("twayair.com",         "티웨이항공",       "물류/교통"),
    ("flowise.co.kr",       "플라이강원",       "물류/교통"),
    ("hanjin.com",          "한진그룹",         "물류/교통"),
    ("cjlogistics.com",     "CJ대한통운",       "물류/교통"),
    ("lotteglogis.com",     "롯데글로벌로지스", "물류/교통"),
    ("hyundailogistics.com","현대로지스틱스",   "물류/교통"),
    ("korail.com",          "코레일",           "물류/교통"),
    ("srail.kr",            "SR(수서고속철도)", "물류/교통"),
    ("seoulmetro.co.kr",    "서울교통공사",     "물류/교통"),
    ("airport.co.kr",       "한국공항공사",     "물류/교통"),
    ("icn.airport.kr",      "인천국제공항",     "공공/기관"),

    # ══ 숙박·여행 ══
    ("yeogi.com",           "여기어때",         "숙박/여행"),
    ("yanolja.com",         "야놀자",           "숙박/여행"),
    ("lottehotel.com",      "롯데호텔",         "숙박/여행"),
    ("shillahotel.com",     "신라호텔",         "숙박/여행"),
    ("interconti.com",      "인터컨티넨탈",     "숙박/여행"),
    ("grand.hyatt.com",     "그랜드하얏트",     "숙박/여행"),
    ("modetour.com",        "모두투어",         "숙박/여행"),
    ("hanatour.com",        "하나투어",         "숙박/여행"),

    # ══ 스타트업·핀테크·SaaS ══
    ("rocketpunch.com",     "로켓펀치",         "전자/IT"),
    ("wanted.co.kr",        "원티드",           "전자/IT"),
    ("jumpit.co.kr",        "점핏",             "전자/IT"),
    ("saramin.co.kr",       "사람인",           "전자/IT"),
    ("jobkorea.co.kr",      "잡코리아",         "전자/IT"),
    ("jobplanet.co.kr",     "잡플래닛",         "전자/IT"),
    ("blind.com",           "블라인드",         "전자/IT"),
    ("channel.io",          "채널톡",           "전자/IT"),
    ("sendbird.com",        "센드버드",         "전자/IT"),
    ("hyperconnect.com",    "하이퍼커넥트",     "전자/IT"),
    ("krafton.com",         "크래프톤",         "게임"),
    ("bucketplace.net",     "오늘의집",         "전자/IT"),
    ("zigbang.com",         "직방",             "전자/IT"),
    ("dabang.com",          "다방",             "전자/IT"),
    ("petproduct.co.kr",    "펫프로덕트",       "반려동물"),
    ("petfriends.co.kr",    "펫프렌즈",         "반려동물"),
    ("fitpet.co.kr",        "핏펫",             "반려동물"),
    ("dogmate.co.kr",       "도그메이트",       "반려동물"),
    ("modusign.co.kr",      "모두싸인",         "전자/IT"),
    ("ridi.com",            "리디",             "전자/IT"),
    ("millie.co.kr",        "밀리의서재",       "전자/IT"),
    ("yes24.com",           "YES24",            "유통/쇼핑"),
    ("aladin.co.kr",        "알라딘",           "유통/쇼핑"),
    ("kyobobook.co.kr",     "교보문고",         "유통/쇼핑"),
    ("naver.com/books",     "네이버시리즈",     "전자/IT"),
    ("webtoon.com",         "웹툰(글로벌)",     "미디어/광고"),
    ("class101.net",        "클래스101",        "전자/IT"),
    ("colosseum.kr",        "콜로세움",         "전자/IT"),
    ("kraftonclub.com",     "크래프톤클럽",     "게임"),
    ("krafton.com",         "배틀그라운드",     "게임"),
    ("bigo.tv",             "비고라이브",       "전자/IT"),
    ("kakaowebtoon.com",    "카카오웹툰",       "미디어/광고"),
    ("nid.naver.com",       "네이버 ID",        "전자/IT"),
    ("payco.com",           "페이코",           "금융/보험"),
    ("samsungpay.com",      "삼성페이",         "금융/보험"),
    ("kakaopay.com",        "카카오페이",       "금융/보험"),
    ("lgpay.com",           "LG페이",           "금융/보험"),
    ("naverpay.me",         "네이버페이",       "금융/보험"),
    ("zeropay.or.kr",       "제로페이",         "금융/보험"),

    # ══ 헬스·피트니스 ══
    ("anytime.kr",          "애니타임피트니스", "건강/의료"),
    ("mcdfit.co.kr",        "맥도날드피트니스", "건강/의료"),
    ("bodyprofile.co.kr",   "바디프로필",       "건강/의료"),
    ("medilive.co.kr",      "메디라이브",       "건강/의료"),
    ("noom.com",            "눔",               "건강/의료"),
    ("samsunghospital.com", "삼성서울병원",     "건강/의료"),
    ("amc.seoul.kr",        "서울아산병원",     "건강/의료"),
    ("snuh.org",            "서울대학교병원",   "건강/의료"),
    ("severance.or.kr",     "세브란스병원",     "건강/의료"),

    # ══ 공공·기관 ══
    ("moe.go.kr",           "교육부",           "공공/기관"),
    ("mohw.go.kr",          "보건복지부",       "공공/기관"),
    ("moef.go.kr",          "기획재정부",       "공공/기관"),
    ("mss.go.kr",           "중소벤처기업부",   "공공/기관"),
    ("kotra.or.kr",         "코트라",           "공공/기관"),
    ("kipo.go.kr",          "특허청",           "공공/기관"),
    ("kftc.or.kr",          "금융결제원",       "공공/기관"),
    ("kcmi.re.kr",          "자본시장연구원",   "공공/기관"),
    ("fss.or.kr",           "금융감독원",       "공공/기관"),
    ("kftc.or.kr",          "금융결제원",       "공공/기관"),
    ("kbia.or.kr",          "보험개발원",       "공공/기관"),
    ("kvca.or.kr",          "벤처캐피탈협회",   "공공/기관"),
    ("kba.or.kr",           "은행연합회",       "공공/기관"),
    ("bok.or.kr",           "한국은행",         "금융/보험"),
    ("krx.co.kr",           "한국거래소",       "금융/보험"),
    ("seoultech.ac.kr",     "서울과학기술대학교","공공/기관"),
    ("snu.ac.kr",           "서울대학교",       "공공/기관"),
    ("yonsei.ac.kr",        "연세대학교",       "공공/기관"),
    ("korea.ac.kr",         "고려대학교",       "공공/기관"),
    ("kaist.ac.kr",         "KAIST",            "공공/기관"),
    ("postech.ac.kr",       "포스텍",           "공공/기관"),
    ("skku.edu",            "성균관대학교",     "공공/기관"),
    ("hanyang.ac.kr",       "한양대학교",       "공공/기관"),
    ("sogang.ac.kr",        "서강대학교",       "공공/기관"),
    ("ewha.ac.kr",          "이화여자대학교",   "공공/기관"),
    ("sookmyung.ac.kr",     "숙명여자대학교",   "공공/기관"),

    # ══ 기타 B2B·산업 ══
    ("doosan.com",          "두산그룹",         "제조/그룹"),
    ("hanjinkal.com",       "한진칼",           "제조/그룹"),
    ("lottecorp.com",       "롯데그룹",         "제조/그룹"),
    ("cj.net",              "CJ그룹",           "제조/그룹"),
    ("gs.co.kr",            "GS그룹",           "제조/그룹"),
    ("hanwha.com",          "한화그룹",         "제조/그룹"),
    ("hd.co.kr",            "HD현대",           "제조/그룹"),
    ("ls-electric.com",     "LS일렉트릭",       "제조/그룹"),
    ("lxinternational.com", "LX인터내셔널",     "제조/그룹"),
    ("hyosung.com",         "효성",             "제조/그룹"),
    ("samsonite.com",       "쌤소나이트",       "뷰티/패션"),
    ("acushnet.com",        "타이틀리스트",     "완구/라이프스타일"),
    ("samsung.com/sec/tv",  "삼성TV",           "전자/IT"),
    ("lgtvplus.com",        "LG채널플러스",     "전자/IT"),
    ("davinci.ai",          "다빈치AI",         "전자/IT"),
    ("ncloud.com",          "네이버클라우드",   "전자/IT"),
    ("kakaocloud.com",      "카카오클라우드",   "전자/IT"),
    ("cloudz.co.kr",        "kt cloud",         "전자/IT"),
    ("sktadmission.co.kr",  "SK텔레콤",         "통신"),
    ("upstage.ai",          "업스테이지",       "전자/IT"),
    ("42dot.ai",            "42dot",            "자동차"),
    ("bespin.global",       "베스핀글로벌",     "전자/IT"),
    ("megazone.com",        "메가존클라우드",   "전자/IT"),
    ("innogrid.com",        "이노그리드",       "전자/IT"),
    ("gabia.com",           "가비아",           "전자/IT"),
    ("cafe24.com",          "카페24",           "전자/IT"),
    ("imweb.me",            "아임웹",           "전자/IT"),
    ("wix.com",             "윅스",             "전자/IT"),
    ("shopify.com",         "쇼피파이",         "전자/IT"),
    ("smartstore.naver.com","네이버스마트스토어","전자/IT"),
    ("talktalk.co.kr",      "SK텔레콤 TalkTalk","통신"),
    ("lghellovision.net",   "LG헬로비전",       "통신"),
    ("dlive.co.kr",         "딜라이브",         "통신"),
    ("pooq.co.kr",          "푹",               "미디어/광고"),
    ("skstoa.com",          "SK스토아",         "유통/쇼핑"),
    ("hyundaihomeshopping.com","현대홈쇼핑",    "유통/쇼핑"),
    ("lotteimall.com",      "롯데아이몰",       "유통/쇼핑"),
    ("hema.com",            "허마(헤마)",       "유통/쇼핑"),
    ("hmall.com",           "H몰",              "유통/쇼핑"),
    ("emart.com",           "이마트",           "유통/쇼핑"),
    ("homeplus.co.kr",      "홈플러스",         "유통/쇼핑"),
    ("lottemart.com",       "롯데마트",         "유통/쇼핑"),
    ("cosco.co.kr",         "코스트코코리아",   "유통/쇼핑"),
    ("ikea.com/kr",         "이케아코리아",     "유통/쇼핑"),
    ("cu.bgfretail.com",    "CU",               "유통/쇼핑"),
    ("gs25.gsretail.com",   "GS25",             "유통/쇼핑"),
    ("7-eleven.co.kr",      "세븐일레븐",       "유통/쇼핑"),
    ("ministop.co.kr",      "미니스톱",         "유통/쇼핑"),
    ("emart24.co.kr",       "이마트24",         "유통/쇼핑"),

    # ══ 2차 배치 ══

    # IT·플랫폼·SaaS
    ("socar.kr",            "쏘카",             "전자/IT"),
    ("pinkfong.com",        "핑크퐁",           "엔터테인먼트"),
    ("krafton.com",         "크래프톤",         "게임"),
    ("kakao.com",           "카카오",           "전자/IT"),
    ("line.me",             "라인",             "전자/IT"),
    ("kakaocorp.com",       "카카오",           "전자/IT"),
    ("nhn.com",             "NHN",              "전자/IT"),
    ("ncsoft.net",          "엔씨소프트",       "게임"),
    ("bandcamp.com",        "밴드캠프",         "미디어/광고"),
    ("band.us",             "밴드",             "전자/IT"),
    ("vlive.tv",            "V LIVE",           "엔터테인먼트"),
    ("weverse.io",          "위버스",           "엔터테인먼트"),
    ("fancafe.daum.net",    "다음팬카페",        "전자/IT"),
    ("nate.com",            "네이트",           "전자/IT"),
    ("cyworld.com",         "싸이월드",         "전자/IT"),
    ("melon.com",           "멜론",             "미디어/광고"),
    ("genie.co.kr",         "지니뮤직",         "미디어/광고"),
    ("bugs.co.kr",          "벅스",             "미디어/광고"),
    ("flo.io",              "FLO",              "미디어/광고"),
    ("vibe.naver.com",      "네이버 바이브",    "미디어/광고"),
    ("youtube.com",         "유튜브",           "미디어/광고"),
    ("kakaopage.com",       "카카오페이지",     "미디어/광고"),
    ("lezhin.com",          "레진코믹스",       "미디어/광고"),
    ("comico.kr",           "코미코",           "미디어/광고"),
    ("toptoon.com",         "탑툰",             "미디어/광고"),
    ("mrblue.com",          "미스터블루",       "미디어/광고"),
    ("munpia.com",          "문피아",           "미디어/광고"),
    ("joara.com",           "조아라",           "미디어/광고"),
    ("kakaoentertainment.com","카카오엔터",     "엔터테인먼트"),
    ("studio-dragon.com",   "스튜디오드래곤",   "엔터테인먼트"),
    ("cjenm.com",           "CJ ENM",           "엔터테인먼트"),
    ("sbs.co.kr",           "SBS",              "미디어/광고"),
    ("ebs.co.kr",           "EBS",              "미디어/광고"),
    ("arirang.com",         "아리랑TV",         "미디어/광고"),
    ("ytnmedia.com",        "YTN",              "미디어/광고"),
    ("mbn.co.kr",           "MBN",              "미디어/광고"),
    ("channela.com",        "채널A",            "미디어/광고"),
    ("tvchosun.com",        "TV조선",           "미디어/광고"),
    ("mt.co.kr",            "머니투데이",       "미디어/광고"),
    ("sedaily.com",         "서울경제",         "미디어/광고"),
    ("thebell.co.kr",       "더벨",             "미디어/광고"),
    ("bloter.net",          "블로터",           "미디어/광고"),

    # 스타트업·유니콘
    ("krafton.com",         "크래프톤",         "게임"),
    ("viva-republica.com",  "비바리퍼블리카",   "금융/보험"),
    ("dunamu.com",          "두나무",           "금융/보험"),
    ("krafton.com",         "크래프톤",         "게임"),
    ("moloco.com",          "몰로코",           "전자/IT"),
    ("rocketdaniel.com",    "로켓다니엘",       "전자/IT"),
    ("kraftoners.com",      "크래프토너스",     "게임"),
    ("creatrip.com",        "크리에이트립",     "숙박/여행"),
    ("travelog.me",         "트래블로그",       "숙박/여행"),
    ("trazy.com",           "트래지",           "숙박/여행"),
    ("triple.guide",        "트리플",           "숙박/여행"),
    ("myrealtrip.com",      "마이리얼트립",     "숙박/여행"),
    ("airbridge.io",        "에어브릿지",       "전자/IT"),
    ("adjust.com",          "에드저스트",       "전자/IT"),
    ("appsflyer.com",       "앱스플라이어",     "전자/IT"),
    ("igaworks.com",        "아이지에이웍스",   "전자/IT"),
    ("nasmedia.co.kr",      "나스미디어",       "미디어/광고"),
    ("dmcmedia.co.kr",      "DMC미디어",        "미디어/광고"),
    ("mezzomedia.co.kr",    "메조미디어",       "미디어/광고"),
    ("vibrantmedia.co.kr",  "바이브런트미디어", "미디어/광고"),
    ("kakaoenterprise.com", "카카오엔터프라이즈","전자/IT"),
    ("kakaowork.com",       "카카오워크",       "전자/IT"),
    ("dooray.com",          "두레이",           "전자/IT"),
    ("jandi.com",           "잔디",             "전자/IT"),
    ("notion.so",           "노션",             "전자/IT"),
    ("slack.com",           "슬랙",             "전자/IT"),
    ("figma.com",           "피그마",           "전자/IT"),
    ("github.com",          "깃허브",           "전자/IT"),
    ("atlassian.com",       "아틀라시안",       "전자/IT"),

    # 금융·핀테크 추가
    ("finda.co.kr",         "핀다",             "금융/보험"),
    ("banksalad.com",       "뱅크샐러드",       "금융/보험"),
    ("tosspayments.com",    "토스페이먼츠",     "금융/보험"),
    ("nicepay.co.kr",       "나이스페이",       "금융/보험"),
    ("inicis.com",          "KG이니시스",       "금융/보험"),
    ("kcp.co.kr",           "NHN KCP",          "금융/보험"),
    ("settle.kr",           "세틀뱅크",         "금융/보험"),
    ("kcb.co.kr",           "코리아크레딧뷰로", "금융/보험"),
    ("siren24.com",         "사이렌24",         "금융/보험"),
    ("naverfinancial.com",  "네이버파이낸셜",   "금융/보험"),
    ("kakaopay.com",        "카카오페이",       "금융/보험"),
    ("samsungcard.com",     "삼성카드",         "금융/보험"),
    ("lottecardco.com",     "롯데카드",         "금융/보험"),
    ("hyundaicapital.com",  "현대캐피탈",       "금융/보험"),
    ("sbijeju.com",         "SBI저축은행",      "금융/보험"),
    ("okfinancialgroup.com","OK금융그룹",       "금융/보험"),
    ("welcomebank.co.kr",   "웰컴저축은행",     "금융/보험"),
    ("hanacard.co.kr",      "하나카드",         "금융/보험"),
    ("nh.co.kr",            "NH증권",           "금융/보험"),
    ("db.com",              "DB그룹",           "금융/보험"),
    ("meritz.co.kr",        "메리츠금융",       "금융/보험"),
    ("kyobolife.co.kr",     "교보생명",         "금융/보험"),
    ("hanwhalife.com",      "한화생명",         "금융/보험"),
    ("samsunglife.com",     "삼성생명",         "금융/보험"),
    ("lgnsons.com",         "LG N소프트",       "전자/IT"),

    # 뷰티·패션 추가
    ("dear-klairs.com",     "클레어스",         "뷰티/패션"),
    ("anua.kr",             "아누아",           "뷰티/패션"),
    ("beauty-of-joseon.com","조선미녀",         "뷰티/패션"),
    ("rovectin.com",        "로벡틴",           "뷰티/패션"),
    ("aclabkorea.com",      "AC래보",           "뷰티/패션"),
    ("medicube.com",        "메디큐브",         "뷰티/패션"),
    ("dr.jart.com",         "닥터자르트",       "뷰티/패션"),
    ("drjart.com",          "닥터자르트",       "뷰티/패션"),
    ("roundlab.co.kr",      "라운드랩",         "뷰티/패션"),
    ("tocobo.com",          "토코보",           "뷰티/패션"),
    ("numbuzin.com",        "넘버즈인",         "뷰티/패션"),
    ("axis-y.com",          "액시스-와이",      "뷰티/패션"),
    ("goodal.co.kr",        "구달",             "뷰티/패션"),
    ("iope.com",            "아이오페",         "뷰티/패션"),
    ("hera.com",            "헤라",             "뷰티/패션"),
    ("primera.com",         "프리메라",         "뷰티/패션"),
    ("vprove.com",          "브이프루브",       "뷰티/패션"),
    ("espoir.com",          "에스쁘아",         "뷰티/패션"),
    ("banilaco.com",        "바닐라코",         "뷰티/패션"),
    ("holika.co.kr",        "홀리카홀리카",     "뷰티/패션"),
    ("skinfood.com",        "스킨푸드",         "뷰티/패션"),
    ("thefaceshop.com",     "더페이스샵",       "뷰티/패션"),
    ("naturerepublic.com",  "네이처리퍼블릭",   "뷰티/패션"),
    ("toonycolor.com",      "투니컬러",         "뷰티/패션"),
    ("laneige.com",         "라네즈",           "뷰티/패션"),
    ("mamonde.com",         "마몽드",           "뷰티/패션"),
    ("karitiful.com",       "카리티풀",         "뷰티/패션"),
    ("ohui.com",            "오휘",             "뷰티/패션"),
    ("whoo.com",            "후",               "뷰티/패션"),
    ("su-m.com",            "숨37",             "뷰티/패션"),
    ("vnk.co.kr",           "빈폴",             "뷰티/패션"),
    ("kuho.com",            "구호",             "뷰티/패션"),
    ("sjyc.co.kr",          "신세계인터내셔날", "뷰티/패션"),
    ("avellano.com",        "아벨라노",         "뷰티/패션"),
    ("87mm.kr",             "87MM",             "뷰티/패션"),
    ("ader-error.com",      "아더에러",         "뷰티/패션"),
    ("pushbutton.co.kr",    "푸시버튼",         "뷰티/패션"),
    ("greedilous.com",      "그리딜러스",       "뷰티/패션"),

    # 식품·외식 추가
    ("nongshim.co.kr",      "농심",             "식품/음료"),
    ("pulmuone.co.kr",      "풀무원",           "식품/음료"),
    ("maeil.com",           "매일유업",         "식품/음료"),
    ("namyang.co.kr",       "남양유업",         "식품/음료"),
    ("yoplait.co.kr",       "요플레",           "식품/음료"),
    ("dongwonf.com",        "동원참치",         "식품/음료"),
    ("ourhome.co.kr",       "아워홈",           "식품/음료"),
    ("ssg-living.com",      "SSG푸드마켓",      "식품/음료"),
    ("freshways.co.kr",     "프레시웨이",       "식품/음료"),
    ("gfresh.co.kr",        "지에프레쉬",       "식품/음료"),
    ("haccp.or.kr",         "식품안전관리원",   "공공/기관"),
    ("lotteconfectionery.com","롯데제과",       "식품/음료"),
    ("crownconfectionery.com","크라운제과",     "식품/음료"),
    ("hite-jinro.com",      "하이트진로",       "식품/음료"),
    ("ob.co.kr",            "OB맥주",           "식품/음료"),
    ("kloud.co.kr",         "클라우드",         "식품/음료"),
    ("terrakorea.com",      "테라",             "식품/음료"),
    ("konjiam.co.kr",       "곤지암리조트",     "숙박/여행"),
    ("gildong.com",         "길동무",           "식품/음료"),
    ("paldo.co.kr",         "팔도",             "식품/음료"),
    ("sempio.com",          "샘표",             "식품/음료"),
    ("haechandle.co.kr",    "해찬들",           "식품/음료"),
    ("daesang.com",         "대상",             "식품/음료"),
    ("chungjungone.com",    "청정원",           "식품/음료"),
    ("cj.co.kr",            "CJ",               "식품/음료"),
    ("mchan.co.kr",         "모차",             "식품/음료"),
    ("theborn.co.kr",       "더본코리아",       "식품/음료"),
    ("jennie.co.kr",        "제니레시피",       "식품/음료"),

    # 제약·바이오 추가
    ("boryung.co.kr",       "보령",             "제약/의료"),
    ("ildongpharm.co.kr",   "일동제약",         "제약/의료"),
    ("yungjin.com",         "영진약품",         "제약/의료"),
    ("taejoon-pharm.com",   "태준제약",         "제약/의료"),
    ("kwangdong.co.kr",     "광동제약",         "제약/의료"),
    ("choongwae.com",       "중외제약",         "제약/의료"),
    ("pharmicell.com",      "파미셀",           "제약/의료"),
    ("helixmith.com",       "헬릭스미스",       "제약/의료"),
    ("genoray.com",         "제노레이",         "제약/의료"),
    ("osstem.com",          "오스템임플란트",   "제약/의료"),
    ("dio.co.kr",           "디오",             "제약/의료"),
    ("dentium.com",         "덴티움",           "제약/의료"),
    ("bioneer.com",         "바이오니어",       "제약/의료"),
    ("genexine.com",        "제넥신",           "제약/의료"),
    ("abcam.com",           "압캠",             "제약/의료"),
    ("hugel.co.kr",         "휴젤",             "제약/의료"),
    ("medytox.com",         "메디톡스",         "제약/의료"),
    ("parexel.com",         "패렉셀",           "제약/의료"),
    ("scinai.com",          "사이나이이뮤노",   "제약/의료"),

    # 교육 추가
    ("megastudy.net",       "메가스터디",       "전자/IT"),
    ("etoos.com",           "이투스",           "전자/IT"),
    ("ebsi.co.kr",          "EBS영어",          "공공/기관"),
    ("visang.com",          "비상교육",         "전자/IT"),
    ("chunjae.co.kr",       "천재교육",         "전자/IT"),
    ("mirae-n.com",         "미래엔",           "전자/IT"),
    ("kyohak.co.kr",        "교학사",           "전자/IT"),
    ("durunet.com",         "두루넷",           "전자/IT"),
    ("eduwill.net",         "에듀윌",           "전자/IT"),
    ("hakken.co.kr",        "해커스",           "전자/IT"),
    ("sisa.co.kr",          "시사닷컴",         "전자/IT"),
    ("yanadoo.com",         "야나두",           "전자/IT"),
    ("ringleplus.com",      "링글",             "전자/IT"),
    ("tutorvista.com",      "튜터비스타",       "전자/IT"),
    ("mathflat.com",        "매쓰플랫",         "전자/IT"),
    ("classting.com",       "클래스팅",         "전자/IT"),
    ("kidsnote.com",        "키즈노트",         "전자/IT"),
    ("carrot.kr",           "당근",             "전자/IT"),
    ("solvook.com",         "쏠북",             "전자/IT"),

    # 물류·배달 추가
    ("woowa.net",           "우아한형제들",     "전자/IT"),
    ("cjons.com",           "CJ올리브네트웍스", "전자/IT"),
    ("lottelogis.com",      "롯데로지스틱스",   "물류/교통"),
    ("hanjinexpress.com",   "한진택배",         "물류/교통"),
    ("cjlogistics.com",     "CJ대한통운",       "물류/교통"),
    ("sfkorea.com",         "SF익스프레스코리아","물류/교통"),
    ("kuronekoservice.com", "야마토운수",       "물류/교통"),
    ("dhl.co.kr",           "DHL코리아",        "물류/교통"),
    ("fedex.com/ko",        "페덱스코리아",     "물류/교통"),
    ("ups.com",             "UPS코리아",        "물류/교통"),
    ("kpost.or.kr",         "우정사업본부",     "공공/기관"),
    ("epost.go.kr",         "우체국",           "공공/기관"),
    ("quickservice.co.kr",  "퀵서비스",         "물류/교통"),
    ("vroong.com",          "부릉",             "물류/교통"),
    ("barogo.com",          "바로고",           "물류/교통"),
    ("meshkorea.net",       "메쉬코리아",       "물류/교통"),

    # 여행·숙박 추가
    ("booking.com",         "부킹닷컴",         "숙박/여행"),
    ("expedia.co.kr",       "익스피디아",       "숙박/여행"),
    ("agoda.com",           "아고다",           "숙박/여행"),
    ("airbnb.co.kr",        "에어비앤비",       "숙박/여행"),
    ("klook.com",           "클룩",             "숙박/여행"),
    ("interpark.com",       "인터파크투어",     "숙박/여행"),
    ("tourvis.com",         "투어비스",         "숙박/여행"),
    ("naeilro.com",         "내일로",           "숙박/여행"),
    ("hotels.com",          "호텔스닷컴",       "숙박/여행"),
    ("marriott.com",        "메리어트",         "숙박/여행"),
    ("hilton.com",          "힐튼",             "숙박/여행"),
    ("paradise.co.kr",      "파라다이스호텔",   "숙박/여행"),
    ("walkerhill.com",      "워커힐호텔",       "숙박/여행"),
    ("konestay.com",        "코네스테이",       "숙박/여행"),
    ("grandwalkerhill.com", "그랜드워커힐",     "숙박/여행"),
    ("skresorts.com",       "SK리조트",         "숙박/여행"),

    # 건설·부동산 추가
    ("aptner.com",          "아파트너",         "건설/부동산"),
    ("zigbang.com",         "직방",             "건설/부동산"),
    ("dabang.com",          "다방",             "건설/부동산"),
    ("naver.land",          "네이버부동산",     "건설/부동산"),
    ("kb-land.co.kr",       "KB부동산",         "건설/부동산"),
    ("xn--289a4xz10btgah.com","직방",          "건설/부동산"),
    ("richgo.co.kr",        "리치고",           "건설/부동산"),
    ("aptok.co.kr",         "아파트OK",         "건설/부동산"),
    ("hogangnono.com",      "호갱노노",         "건설/부동산"),
    ("lotteconstruction.co.kr","롯데건설",      "건설/부동산"),
    ("skecoplant.com",      "SK에코플랜트",     "건설/부동산"),
    ("hyundaielevator.com", "현대엘리베이터",   "건설/부동산"),
    ("otis.co.kr",          "오티스엘리베이터", "건설/부동산"),

    # 에너지·환경 추가
    ("hanwhasolarenergy.com","한화에너지",      "에너지/화학"),
    ("ls-electric.com",     "LS일렉트릭",       "에너지/화학"),
    ("doosan-enerbilty.com","두산에너빌리티",   "에너지/화학"),
    ("hyundaienergy.co.kr", "현대에너지솔루션", "에너지/화학"),
    ("ssangyong.co.kr",     "쌍용에너지",       "에너지/화학"),
    ("solarfarm.kr",        "솔라팜",           "에너지/화학"),
    ("enelx.com",           "에넬X",            "에너지/화학"),
    ("env.go.kr",           "환경부",           "공공/기관"),
    ("waterworks.seoul.kr", "서울시상수도사업본부","공공/기관"),
    ("keei.re.kr",          "에너지경제연구원", "공공/기관"),

    # 공공·기관 추가
    ("police.go.kr",        "경찰청",           "공공/기관"),
    ("nia.or.kr",           "한국정보화진흥원", "공공/기관"),
    ("kist.re.kr",          "한국과학기술연구원","공공/기관"),
    ("etri.re.kr",          "한국전자통신연구원","공공/기관"),
    ("kitech.re.kr",        "한국생산기술연구원","공공/기관"),
    ("krict.re.kr",         "한국화학연구원",   "공공/기관"),
    ("kimm.re.kr",          "한국기계연구원",   "공공/기관"),
    ("kari.re.kr",          "한국항공우주연구원","공공/기관"),
    ("naek.or.kr",          "한국공학한림원",   "공공/기관"),
    ("nrf.re.kr",           "한국연구재단",     "공공/기관"),
    ("iitp.kr",             "정보통신기획평가원","공공/기관"),
    ("kca.kr",              "한국방송통신전파진흥원","공공/기관"),
    ("kocca.or.kr",         "한국콘텐츠진흥원", "공공/기관"),
    ("kto.visitkorea.or.kr","한국관광공사",     "공공/기관"),
    ("k-startup.go.kr",     "창업진흥원",       "공공/기관"),
    ("nipa.kr",             "정보통신산업진흥원","공공/기관"),
    ("kisa.or.kr",          "한국인터넷진흥원", "공공/기관"),
    ("kcc.go.kr",           "방송통신위원회",   "공공/기관"),
    ("msit.go.kr",          "과학기술정보통신부","공공/기관"),
    ("motie.go.kr",         "산업통상자원부",   "공공/기관"),
    ("mlit.go.kr",          "국토교통부",       "공공/기관"),

    # 완구·생활 추가
    ("youngtoys.com",       "영실업",           "완구/라이프스타일"),
    ("sonokong.co.kr",      "손오공",           "완구/라이프스타일"),
    ("playdo.co.kr",        "플레이도",         "완구/라이프스타일"),
    ("lego.com/ko",         "레고코리아",       "완구/라이프스타일"),
    ("mattel.com/ko",       "마텔코리아",       "완구/라이프스타일"),
    ("cuckoo.co.kr",        "쿠쿠",             "전자/IT"),
    ("lg.com/ko/home-appliance","LG가전",       "전자/IT"),
    ("samsung.com/sec/home","삼성가전",         "전자/IT"),
    ("dyson.co.kr",         "다이슨코리아",     "전자/IT"),
    ("roomba.co.kr",        "룸바코리아",       "전자/IT"),
    ("irobot.co.kr",        "아이로봇코리아",   "전자/IT"),
    ("ecovacs.com/kr",      "에코백스",         "전자/IT"),
    ("roborock.com/kr",     "로보락",           "전자/IT"),
    ("xiaomi.co.kr",        "샤오미코리아",     "전자/IT"),
    ("huawei.com/kr",       "화웨이코리아",     "전자/IT"),
    ("apple.com/kr",        "애플코리아",       "전자/IT"),
    ("microsoft.com/ko",    "마이크로소프트",   "전자/IT"),
    ("google.co.kr",        "구글코리아",       "전자/IT"),
    ("amazon.co.kr",        "아마존코리아",     "전자/IT"),
]

def load_existing() -> tuple[set, dict]:
    if not BRANDS_JSON.exists():
        return set(), {"total": 0, "source": "vibers-logo-db", "brands": []}
    data = json.loads(BRANDS_JSON.read_text())
    existing = set()
    for b in data.get("brands", []):
        existing.add(b["id"])
        if b.get("domain"):
            existing.add(b["domain"])
    return existing, data


def domain_to_id(domain: str) -> str:
    base = domain.split("/")[0]
    slug = re.sub(r"\.[a-z]{2,6}$", "", base)
    slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
    return slug


def fetch_logo(domain: str, brand_id: str, name_ko: str) -> bool:
    base_domain = domain.split("/")[0]
    url = f"https://img.logo.dev/{base_domain}?token={TOKEN}&size=400&format=png"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status != 200:
                return False
            raw = r.read()
        if len(raw) < 2000:
            print(f"     ⚠️  너무 작음 ({len(raw)}B) — placeholder 추정")
            return False
        dest = LOGO_DIR / brand_id
        dest.mkdir(parents=True, exist_ok=True)
        safe_write(dest / "logo.png", raw)
        print(f"     ✅ {len(raw):,}B")
        return True
    except Exception as e:
        print(f"     ❌ {e}")
        return False


def run_pipeline(brand_id: str):
    import subprocess as sp
    sp.run([sys.executable, str(BASE / "build-variants.py"), "--brand", brand_id],
           cwd=BASE, capture_output=True, timeout=60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--no-pipeline", action="store_true")
    args = parser.parse_args()

    existing, data = load_existing()
    existing_ids = {b["id"] for b in data["brands"]}
    brand_map = {b["id"]: b for b in data["brands"]}

    seen_domains = set()
    added = []

    for domain, name_ko, category in KR_DOMAINS:
        base_domain = domain.split("/")[0]
        brand_id = domain_to_id(base_domain)

        if brand_id in existing_ids or base_domain in existing or brand_id in seen_domains:
            print(f"  ⏭  {brand_id} (이미 있음)")
            continue
        seen_domains.add(brand_id)

        print(f"  🔍 {brand_id} — {name_ko} ({base_domain})")

        if args.dry_run:
            added.append(brand_id)
            continue

        ok = fetch_logo(base_domain, brand_id, name_ko)
        if not ok:
            continue

        entry = {
            "id": brand_id,
            "name_ko": name_ko,
            "name_en": name_ko,
            "category": category,
            "domain": base_domain,
            "logo_svg": False,
            "source": f"logo.dev:{base_domain}",
            "status": "raw",
        }
        data["brands"].append(entry)
        existing_ids.add(brand_id)
        added.append(brand_id)
        time.sleep(0.4)

        if not args.no_pipeline:
            run_pipeline(brand_id)

        time.sleep(0.2)

    if args.dry_run:
        print(f"\n📋 수집 예정: {len(added)}개")
        for b in added:
            print(f"  {b}")
        return

    if not added:
        print("\n✨ 신규 브랜드 없음")
        return

    data["total"] = len(data["brands"])
    BRANDS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\n📝 brands.json 업데이트: +{len(added)}개 (총 {data['total']}개)")

    if args.commit:
        import subprocess as sp
        sp.run(["git", "add", "_clients/"], cwd=BASE)
        msg = f"feat: logo.dev 수집 +{len(added)}개 ({', '.join(added[:5])}{'...' if len(added) > 5 else ''})"
        sp.run(["git", "commit", "-m", msg], cwd=BASE)
        sp.run(["git", "push", "origin", "main"], cwd=BASE)
        print("  ✅ push 완료")

    print(f"\n✅ 완료: {len(added)}개 수집")


if __name__ == "__main__":
    main()
