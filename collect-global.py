#!/usr/bin/env python3
"""
글로벌 브랜드 로고 수집 스크립트 — collect-global.py

소스:
  1. Simple Icons (simpleicons.org) — SVG, 무제한 무료
  2. Clearbit Logo API — PNG, 무제한 무료

실행:
  python3 collect-global.py              # 전체 수집
  python3 collect-global.py --dry-run    # 다운로드 없이 목록만 확인
  python3 collect-global.py --cat AI     # 특정 카테고리만
  python3 collect-global.py --force      # 이미 존재하는 것도 덮어쓰기

================================================================================
  ★ 브랜드 추가/수정 방법 ★
  아래 BRANDS 딕셔너리에 항목을 추가하세요.

  포맷:
    "brand-id": {
        "name_ko": "한국어 이름",
        "name_en": "English Name",
        "category": "카테고리",        # 아래 CATEGORIES 목록 참고
        "simple_icon": "slug",         # simpleicons.org 슬러그 (없으면 None)
        "domain": "example.com",       # Clearbit PNG 다운로드용 (없으면 None)
        "color": "#FF6B35",            # 브랜드 대표 색상 (선택)
    },

  Simple Icons 슬러그 확인: https://simpleicons.org 에서 아이콘 클릭 → slug 확인
================================================================================
"""

# 저장 가드 — 확장자와 내용이 다르면 쓰지 않는다 (404 HTML 이 logo.svg 로
# 저장되던 사고 재발 방지).
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent / "scripts"))
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from assetguard import safe_write


import argparse, json, os, re, time, urllib.request
from datetime import date
from pathlib import Path

BASE       = Path(__file__).parent
LOGO_DIR   = BASE / "_clients"
BRANDS_JSON = LOGO_DIR / "brands.json"
UA = "VibersLogoDB/1.0 (vibers.leo@gmail.com)"

SI_CDN   = "https://cdn.simpleicons.org/{slug}"           # Simple Icons SVG CDN
SI_RAW   = "https://raw.githubusercontent.com/simple-icons/simple-icons/HEAD/icons/{slug}.svg"
CLEARBIT = "https://logo.clearbit.com/{domain}?size=800"  # Clearbit PNG

# ============================================================
#  카테고리 목록 (기존 brands.json과 통일)
# ============================================================
CATEGORIES = [
    "AI·머신러닝",
    "암호화폐·블록체인",
    "금융·결제",
    "자동차",
    "IT·클라우드",
    "소프트웨어·개발",
    "전자/IT",       # 기존 카테고리
    "게임",
    "소셜미디어",
    "엔터테인먼트",
]

# ============================================================
#  ★ 수집 대상 브랜드 목록 — 여기를 편집하세요 ★
# ============================================================
BRANDS: dict[str, dict] = {

    # ─── AI·머신러닝 ────────────────────────────────────────
    "openai": {
        "name_ko": "OpenAI",
        "name_en": "OpenAI",
        "category": "AI·머신러닝",
        "simple_icon": "openai",
        "domain": "openai.com",
    },
    "anthropic": {
        "name_ko": "Anthropic",
        "name_en": "Anthropic",
        "category": "AI·머신러닝",
        "simple_icon": "anthropic",
        "domain": "anthropic.com",
    },
    "huggingface": {
        "name_ko": "허깅페이스",
        "name_en": "Hugging Face",
        "category": "AI·머신러닝",
        "simple_icon": "huggingface",
        "domain": "huggingface.co",
    },
    "nvidia": {
        "name_ko": "엔비디아",
        "name_en": "NVIDIA",
        "category": "AI·머신러닝",
        "simple_icon": "nvidia",
        "domain": "nvidia.com",
    },
    "mistralai": {
        "name_ko": "미스트랄 AI",
        "name_en": "Mistral AI",
        "category": "AI·머신러닝",
        "simple_icon": "mistralai",
        "domain": "mistral.ai",
    },
    "perplexityai": {
        "name_ko": "퍼플렉시티",
        "name_en": "Perplexity AI",
        "category": "AI·머신러닝",
        "simple_icon": "perplexity",
        "domain": "perplexity.ai",
    },
    "ollama": {
        "name_ko": "올라마",
        "name_en": "Ollama",
        "category": "AI·머신러닝",
        "simple_icon": "ollama",
        "domain": "ollama.com",
    },
    "deepmind": {
        "name_ko": "구글 딥마인드",
        "name_en": "Google DeepMind",
        "category": "AI·머신러닝",
        "simple_icon": "deepmind",
        "domain": "deepmind.google",
    },
    "stability-ai": {
        "name_ko": "스태빌리티 AI",
        "name_en": "Stability AI",
        "category": "AI·머신러닝",
        "simple_icon": "stabilityai",
        "domain": "stability.ai",
    },
    "cursor": {
        "name_ko": "커서",
        "name_en": "Cursor",
        "category": "AI·머신러닝",
        "simple_icon": "cursor",
        "domain": "cursor.com",
    },

    # ─── 암호화폐·블록체인 ───────────────────────────────────
    "bitcoin": {
        "name_ko": "비트코인",
        "name_en": "Bitcoin",
        "category": "암호화폐·블록체인",
        "simple_icon": "bitcoin",
        "domain": "bitcoin.org",
    },
    "ethereum": {
        "name_ko": "이더리움",
        "name_en": "Ethereum",
        "category": "암호화폐·블록체인",
        "simple_icon": "ethereum",
        "domain": "ethereum.org",
    },
    "binance": {
        "name_ko": "바이낸스",
        "name_en": "Binance",
        "category": "암호화폐·블록체인",
        "simple_icon": "binance",
        "domain": "binance.com",
    },
    "coinbase": {
        "name_ko": "코인베이스",
        "name_en": "Coinbase",
        "category": "암호화폐·블록체인",
        "simple_icon": "coinbase",
        "domain": "coinbase.com",
    },
    "chainlink": {
        "name_ko": "체인링크",
        "name_en": "Chainlink",
        "category": "암호화폐·블록체인",
        "simple_icon": "chainlink",
        "domain": "chain.link",
    },
    "solana": {
        "name_ko": "솔라나",
        "name_en": "Solana",
        "category": "암호화폐·블록체인",
        "simple_icon": "solana",
        "domain": "solana.com",
    },
    "dogecoin": {
        "name_ko": "도지코인",
        "name_en": "Dogecoin",
        "category": "암호화폐·블록체인",
        "simple_icon": "dogecoin",
        "domain": "dogecoin.com",
    },
    "cardano": {
        "name_ko": "카르다노",
        "name_en": "Cardano",
        "category": "암호화폐·블록체인",
        "simple_icon": "cardano",
        "domain": "cardano.org",
    },
    "polygon": {
        "name_ko": "폴리곤",
        "name_en": "Polygon",
        "category": "암호화폐·블록체인",
        "simple_icon": "polygon",
        "domain": "polygon.technology",
    },
    "metamask": {
        "name_ko": "메타마스크",
        "name_en": "MetaMask",
        "category": "암호화폐·블록체인",
        "simple_icon": "metamask",
        "domain": "metamask.io",
    },
    "opensea": {
        "name_ko": "오픈씨",
        "name_en": "OpenSea",
        "category": "암호화폐·블록체인",
        "simple_icon": "opensea",
        "domain": "opensea.io",
    },
    "uniswap": {
        "name_ko": "유니스왑",
        "name_en": "Uniswap",
        "category": "암호화폐·블록체인",
        "simple_icon": None,  # Simple Icons 미지원 → Clearbit만
        "domain": "uniswap.org",
    },
    "kraken": {
        "name_ko": "크라켄",
        "name_en": "Kraken",
        "category": "암호화폐·블록체인",
        "simple_icon": "kraken",
        "domain": "kraken.com",
    },
    "tether": {
        "name_ko": "테더",
        "name_en": "Tether",
        "category": "암호화폐·블록체인",
        "simple_icon": "tether",
        "domain": "tether.to",
    },
    "xrp": {
        "name_ko": "리플",
        "name_en": "XRP / Ripple",
        "category": "암호화폐·블록체인",
        "simple_icon": "xrp",
        "domain": "ripple.com",
    },

    # ─── 금융·결제 ──────────────────────────────────────────
    "visa": {
        "name_ko": "비자",
        "name_en": "Visa",
        "category": "금융·결제",
        "simple_icon": "visa",
        "domain": "visa.com",
    },
    "mastercard": {
        "name_ko": "마스터카드",
        "name_en": "Mastercard",
        "category": "금융·결제",
        "simple_icon": "mastercard",
        "domain": "mastercard.com",
    },
    "paypal": {
        "name_ko": "페이팔",
        "name_en": "PayPal",
        "category": "금융·결제",
        "simple_icon": "paypal",
        "domain": "paypal.com",
    },
    "stripe": {
        "name_ko": "스트라이프",
        "name_en": "Stripe",
        "category": "금융·결제",
        "simple_icon": "stripe",
        "domain": "stripe.com",
    },
    "american-express": {
        "name_ko": "아메리칸 익스프레스",
        "name_en": "American Express",
        "category": "금융·결제",
        "simple_icon": "americanexpress",
        "domain": "americanexpress.com",
    },
    "revolut": {
        "name_ko": "레볼루트",
        "name_en": "Revolut",
        "category": "금융·결제",
        "simple_icon": "revolut",
        "domain": "revolut.com",
    },
    "klarna": {
        "name_ko": "클라르나",
        "name_en": "Klarna",
        "category": "금융·결제",
        "simple_icon": "klarna",
        "domain": "klarna.com",
    },
    "wise": {
        "name_ko": "와이즈",
        "name_en": "Wise",
        "category": "금융·결제",
        "simple_icon": "wise",
        "domain": "wise.com",
    },
    "square": {
        "name_ko": "스퀘어",
        "name_en": "Square",
        "category": "금융·결제",
        "simple_icon": "square",
        "domain": "squareup.com",
    },
    "goldman-sachs": {
        "name_ko": "골드만삭스",
        "name_en": "Goldman Sachs",
        "category": "금융·결제",
        "simple_icon": "goldmansachs",
        "domain": "goldmansachs.com",
    },
    "bloomberg": {
        "name_ko": "블룸버그",
        "name_en": "Bloomberg",
        "category": "금융·결제",
        "simple_icon": None,  # Simple Icons 미지원 → Clearbit만
        "domain": "bloomberg.com",
    },

    # ─── 자동차 ─────────────────────────────────────────────
    "tesla": {
        "name_ko": "테슬라",
        "name_en": "Tesla",
        "category": "자동차",
        "simple_icon": "tesla",
        "domain": "tesla.com",
    },
    "toyota": {
        "name_ko": "도요타",
        "name_en": "Toyota",
        "category": "자동차",
        "simple_icon": "toyota",
        "domain": "toyota.com",
    },
    "bmw": {
        "name_ko": "BMW",
        "name_en": "BMW",
        "category": "자동차",
        "simple_icon": "bmw",
        "domain": "bmw.com",
    },
    "volkswagen": {
        "name_ko": "폭스바겐",
        "name_en": "Volkswagen",
        "category": "자동차",
        "simple_icon": "volkswagen",
        "domain": "volkswagen.com",
    },
    "audi": {
        "name_ko": "아우디",
        "name_en": "Audi",
        "category": "자동차",
        "simple_icon": "audi",
        "domain": "audi.com",
    },
    "mercedes-benz": {
        "name_ko": "메르세데스-벤츠",
        "name_en": "Mercedes-Benz",
        "category": "자동차",
        "simple_icon": None,  # Simple Icons 미지원 → Clearbit만
        "domain": "mercedes-benz.com",
    },
    "ford": {
        "name_ko": "포드",
        "name_en": "Ford",
        "category": "자동차",
        "simple_icon": "ford",
        "domain": "ford.com",
    },
    "honda": {
        "name_ko": "혼다",
        "name_en": "Honda",
        "category": "자동차",
        "simple_icon": "honda",
        "domain": "honda.com",
    },
    "rivian": {
        "name_ko": "리비안",
        "name_en": "Rivian",
        "category": "자동차",
        "simple_icon": None,  # Simple Icons 미지원 → Clearbit만
        "domain": "rivian.com",
    },
    "porsche": {
        "name_ko": "포르쉐",
        "name_en": "Porsche",
        "category": "자동차",
        "simple_icon": "porsche",
        "domain": "porsche.com",
    },
    "volvo": {
        "name_ko": "볼보",
        "name_en": "Volvo",
        "category": "자동차",
        "simple_icon": "volvo",
        "domain": "volvo.com",
    },
    "lamborghini": {
        "name_ko": "람보르기니",
        "name_en": "Lamborghini",
        "category": "자동차",
        "simple_icon": "lamborghini",
        "domain": "lamborghini.com",
    },
    "ferrari": {
        "name_ko": "페라리",
        "name_en": "Ferrari",
        "category": "자동차",
        "simple_icon": "ferrari",
        "domain": "ferrari.com",
    },
    "lucidmotors": {
        "name_ko": "루시드 모터스",
        "name_en": "Lucid Motors",
        "category": "자동차",
        "simple_icon": "lucid",
        "domain": "lucidmotors.com",
    },

    # ─── IT·클라우드 ─────────────────────────────────────────
    "aws": {
        "name_ko": "아마존 웹서비스",
        "name_en": "Amazon Web Services",
        "category": "IT·클라우드",
        "simple_icon": "amazonwebservices",
        "domain": "aws.amazon.com",
    },
    "google-cloud": {
        "name_ko": "구글 클라우드",
        "name_en": "Google Cloud",
        "category": "IT·클라우드",
        "simple_icon": "googlecloud",
        "domain": "cloud.google.com",
    },
    "microsoft-azure": {
        "name_ko": "마이크로소프트 애저",
        "name_en": "Microsoft Azure",
        "category": "IT·클라우드",
        "simple_icon": "microsoftazure",
        "domain": "azure.microsoft.com",
    },
    "cloudflare": {
        "name_ko": "클라우드플레어",
        "name_en": "Cloudflare",
        "category": "IT·클라우드",
        "simple_icon": "cloudflare",
        "domain": "cloudflare.com",
    },
    "vercel": {
        "name_ko": "버셀",
        "name_en": "Vercel",
        "category": "IT·클라우드",
        "simple_icon": "vercel",
        "domain": "vercel.com",
    },
    "netlify": {
        "name_ko": "넷리파이",
        "name_en": "Netlify",
        "category": "IT·클라우드",
        "simple_icon": "netlify",
        "domain": "netlify.com",
    },
    "digitalocean": {
        "name_ko": "디지털오션",
        "name_en": "DigitalOcean",
        "category": "IT·클라우드",
        "simple_icon": "digitalocean",
        "domain": "digitalocean.com",
    },
    "supabase": {
        "name_ko": "수파베이스",
        "name_en": "Supabase",
        "category": "IT·클라우드",
        "simple_icon": "supabase",
        "domain": "supabase.com",
    },
    "firebase": {
        "name_ko": "파이어베이스",
        "name_en": "Firebase",
        "category": "IT·클라우드",
        "simple_icon": "firebase",
        "domain": "firebase.google.com",
    },
    "salesforce": {
        "name_ko": "세일즈포스",
        "name_en": "Salesforce",
        "category": "IT·클라우드",
        "simple_icon": "salesforce",
        "domain": "salesforce.com",
    },
    "oracle": {
        "name_ko": "오라클",
        "name_en": "Oracle",
        "category": "IT·클라우드",
        "simple_icon": "oracle",
        "domain": "oracle.com",
    },
    "ibm": {
        "name_ko": "IBM",
        "name_en": "IBM",
        "category": "IT·클라우드",
        "simple_icon": "ibm",
        "domain": "ibm.com",
    },
    "intel": {
        "name_ko": "인텔",
        "name_en": "Intel",
        "category": "IT·클라우드",
        "simple_icon": "intel",
        "domain": "intel.com",
    },
    "amd": {
        "name_ko": "AMD",
        "name_en": "AMD",
        "category": "IT·클라우드",
        "simple_icon": "amd",
        "domain": "amd.com",
    },
    "qualcomm": {
        "name_ko": "퀄컴",
        "name_en": "Qualcomm",
        "category": "IT·클라우드",
        "simple_icon": "qualcomm",
        "domain": "qualcomm.com",
    },

    # ─── 소프트웨어·개발 ─────────────────────────────────────
    "github": {
        "name_ko": "깃허브",
        "name_en": "GitHub",
        "category": "소프트웨어·개발",
        "simple_icon": "github",
        "domain": "github.com",
    },
    "gitlab": {
        "name_ko": "깃랩",
        "name_en": "GitLab",
        "category": "소프트웨어·개발",
        "simple_icon": "gitlab",
        "domain": "gitlab.com",
    },
    "docker": {
        "name_ko": "도커",
        "name_en": "Docker",
        "category": "소프트웨어·개발",
        "simple_icon": "docker",
        "domain": "docker.com",
    },
    "figma": {
        "name_ko": "피그마",
        "name_en": "Figma",
        "category": "소프트웨어·개발",
        "simple_icon": "figma",
        "domain": "figma.com",
    },
    "notion": {
        "name_ko": "노션",
        "name_en": "Notion",
        "category": "소프트웨어·개발",
        "simple_icon": "notion",
        "domain": "notion.so",
    },
    "slack": {
        "name_ko": "슬랙",
        "name_en": "Slack",
        "category": "소프트웨어·개발",
        "simple_icon": "slack",
        "domain": "slack.com",
    },
    "discord": {
        "name_ko": "디스코드",
        "name_en": "Discord",
        "category": "소프트웨어·개발",
        "simple_icon": "discord",
        "domain": "discord.com",
    },
    "jira": {
        "name_ko": "지라",
        "name_en": "Jira",
        "category": "소프트웨어·개발",
        "simple_icon": "jira",
        "domain": "atlassian.com",
    },
    "confluence": {
        "name_ko": "컨플루언스",
        "name_en": "Confluence",
        "category": "소프트웨어·개발",
        "simple_icon": "confluence",
        "domain": "atlassian.com",
    },
    "vscode": {
        "name_ko": "VS Code",
        "name_en": "Visual Studio Code",
        "category": "소프트웨어·개발",
        "simple_icon": "visualstudiocode",
        "domain": "code.visualstudio.com",
    },
    "jetbrains": {
        "name_ko": "젯브레인스",
        "name_en": "JetBrains",
        "category": "소프트웨어·개발",
        "simple_icon": "jetbrains",
        "domain": "jetbrains.com",
    },
    "linear": {
        "name_ko": "리니어",
        "name_en": "Linear",
        "category": "소프트웨어·개발",
        "simple_icon": "linear",
        "domain": "linear.app",
    },
    "postman": {
        "name_ko": "포스트맨",
        "name_en": "Postman",
        "category": "소프트웨어·개발",
        "simple_icon": "postman",
        "domain": "postman.com",
    },
    "zoom": {
        "name_ko": "줌",
        "name_en": "Zoom",
        "category": "소프트웨어·개발",
        "simple_icon": "zoom",
        "domain": "zoom.us",
    },
    "wordpress": {
        "name_ko": "워드프레스",
        "name_en": "WordPress",
        "category": "소프트웨어·개발",
        "simple_icon": "wordpress",
        "domain": "wordpress.com",
    },
    "shopify": {
        "name_ko": "쇼피파이",
        "name_en": "Shopify",
        "category": "소프트웨어·개발",
        "simple_icon": "shopify",
        "domain": "shopify.com",
    },
    "adobe": {
        "name_ko": "어도비",
        "name_en": "Adobe",
        "category": "소프트웨어·개발",
        "simple_icon": "adobe",
        "domain": "adobe.com",
    },
    "canva": {
        "name_ko": "캔바",
        "name_en": "Canva",
        "category": "소프트웨어·개발",
        "simple_icon": "canva",
        "domain": "canva.com",
    },
    "atlassian": {
        "name_ko": "아틀라시안",
        "name_en": "Atlassian",
        "category": "소프트웨어·개발",
        "simple_icon": "atlassian",
        "domain": "atlassian.com",
    },

    # ─── 전자/IT (글로벌 빅테크) ────────────────────────────
    "apple": {
        "name_ko": "애플",
        "name_en": "Apple",
        "category": "전자/IT",
        "simple_icon": "apple",
        "domain": "apple.com",
    },
    "google": {
        "name_ko": "구글",
        "name_en": "Google",
        "category": "전자/IT",
        "simple_icon": "google",
        "domain": "google.com",
    },
    "microsoft": {
        "name_ko": "마이크로소프트",
        "name_en": "Microsoft",
        "category": "전자/IT",
        "simple_icon": "microsoft",
        "domain": "microsoft.com",
    },
    "meta": {
        "name_ko": "메타",
        "name_en": "Meta",
        "category": "전자/IT",
        "simple_icon": "meta",
        "domain": "meta.com",
    },
    "amazon": {
        "name_ko": "아마존",
        "name_en": "Amazon",
        "category": "전자/IT",
        "simple_icon": "amazon",
        "domain": "amazon.com",
    },
    "alibaba": {
        "name_ko": "알리바바",
        "name_en": "Alibaba",
        "category": "전자/IT",
        "simple_icon": "alibabacloud",  # 알리바바 클라우드 아이콘 사용
        "domain": "alibaba.com",
    },
    "sony": {
        "name_ko": "소니",
        "name_en": "Sony",
        "category": "전자/IT",
        "simple_icon": "sony",
        "domain": "sony.com",
    },
    "xiaomi": {
        "name_ko": "샤오미",
        "name_en": "Xiaomi",
        "category": "전자/IT",
        "simple_icon": "xiaomi",
        "domain": "mi.com",
    },
    "huawei": {
        "name_ko": "화웨이",
        "name_en": "Huawei",
        "category": "전자/IT",
        "simple_icon": "huawei",
        "domain": "huawei.com",
    },
    "asus": {
        "name_ko": "아수스",
        "name_en": "ASUS",
        "category": "전자/IT",
        "simple_icon": "asus",
        "domain": "asus.com",
    },
    "lenovo": {
        "name_ko": "레노버",
        "name_en": "Lenovo",
        "category": "전자/IT",
        "simple_icon": "lenovo",
        "domain": "lenovo.com",
    },
    "dell": {
        "name_ko": "델",
        "name_en": "Dell",
        "category": "전자/IT",
        "simple_icon": "dell",
        "domain": "dell.com",
    },

    # ─── 소셜미디어 ──────────────────────────────────────────
    "youtube": {
        "name_ko": "유튜브",
        "name_en": "YouTube",
        "category": "소셜미디어",
        "simple_icon": "youtube",
        "domain": "youtube.com",
    },
    "instagram": {
        "name_ko": "인스타그램",
        "name_en": "Instagram",
        "category": "소셜미디어",
        "simple_icon": "instagram",
        "domain": "instagram.com",
    },
    "tiktok": {
        "name_ko": "틱톡",
        "name_en": "TikTok",
        "category": "소셜미디어",
        "simple_icon": "tiktok",
        "domain": "tiktok.com",
    },
    "x-twitter": {
        "name_ko": "X (트위터)",
        "name_en": "X / Twitter",
        "category": "소셜미디어",
        "simple_icon": "x",
        "domain": "x.com",
    },
    "threads": {
        "name_ko": "스레드",
        "name_en": "Threads",
        "category": "소셜미디어",
        "simple_icon": "threads",
        "domain": "threads.net",
    },
    "linkedin": {
        "name_ko": "링크드인",
        "name_en": "LinkedIn",
        "category": "소셜미디어",
        "simple_icon": "linkedin",
        "domain": "linkedin.com",
    },
    "reddit": {
        "name_ko": "레딧",
        "name_en": "Reddit",
        "category": "소셜미디어",
        "simple_icon": "reddit",
        "domain": "reddit.com",
    },
    "pinterest": {
        "name_ko": "핀터레스트",
        "name_en": "Pinterest",
        "category": "소셜미디어",
        "simple_icon": "pinterest",
        "domain": "pinterest.com",
    },
    "twitch": {
        "name_ko": "트위치",
        "name_en": "Twitch",
        "category": "소셜미디어",
        "simple_icon": "twitch",
        "domain": "twitch.tv",
    },
    "telegram": {
        "name_ko": "텔레그램",
        "name_en": "Telegram",
        "category": "소셜미디어",
        "simple_icon": "telegram",
        "domain": "telegram.org",
    },
    "whatsapp": {
        "name_ko": "왓츠앱",
        "name_en": "WhatsApp",
        "category": "소셜미디어",
        "simple_icon": "whatsapp",
        "domain": "whatsapp.com",
    },
    "snapchat": {
        "name_ko": "스냅챗",
        "name_en": "Snapchat",
        "category": "소셜미디어",
        "simple_icon": "snapchat",
        "domain": "snapchat.com",
    },

    # ─── 게임 ────────────────────────────────────────────────
    "steam": {
        "name_ko": "스팀",
        "name_en": "Steam",
        "category": "게임",
        "simple_icon": "steam",
        "domain": "steampowered.com",
    },
    "epicgames": {
        "name_ko": "에픽게임즈",
        "name_en": "Epic Games",
        "category": "게임",
        "simple_icon": "epicgames",
        "domain": "epicgames.com",
    },
    "roblox": {
        "name_ko": "로블록스",
        "name_en": "Roblox",
        "category": "게임",
        "simple_icon": "roblox",
        "domain": "roblox.com",
    },
    "unity": {
        "name_ko": "유니티",
        "name_en": "Unity",
        "category": "게임",
        "simple_icon": "unity",
        "domain": "unity.com",
    },
    "unreal-engine": {
        "name_ko": "언리얼 엔진",
        "name_en": "Unreal Engine",
        "category": "게임",
        "simple_icon": "unrealengine",
        "domain": "unrealengine.com",
    },
    "xbox": {
        "name_ko": "엑스박스",
        "name_en": "Xbox",
        "category": "게임",
        "simple_icon": "xbox",
        "domain": "xbox.com",
    },
    "playstation": {
        "name_ko": "플레이스테이션",
        "name_en": "PlayStation",
        "category": "게임",
        "simple_icon": "playstation",
        "domain": "playstation.com",
    },
    "nintendo": {
        "name_ko": "닌텐도",
        "name_en": "Nintendo",
        "category": "게임",
        "simple_icon": None,  # Simple Icons 미지원 → Clearbit만
        "domain": "nintendo.com",
    },
}


# ============================================================
#  수집 로직 (편집 불필요)
# ============================================================

def si_slug_to_url(slug: str) -> str:
    return SI_CDN.format(slug=slug)

def si_raw_url(slug: str) -> str:
    return SI_RAW.format(slug=slug)

def download(url: str, dest: Path, retries=2) -> bool:
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 200:
                    return safe_write(dest, r.read())
        except Exception as e:
            if attempt == retries:
                print(f"    ✗ 다운로드 실패: {url} ({e})")
            else:
                time.sleep(1)
    return False

def svg_set_black(svg_text: str) -> str:
    """SVG의 fill 색상을 모두 currentColor로 변환 (다크모드 대응)"""
    return svg_text  # Simple Icons SVG는 이미 단일 색상

def load_brands() -> list:
    if not BRANDS_JSON.exists():
        return []
    d = json.loads(BRANDS_JSON.read_text())
    return d if isinstance(d, list) else d.get("brands", [])

def save_brands(brands: list):
    existing = json.loads(BRANDS_JSON.read_text()) if BRANDS_JSON.exists() else {}
    if isinstance(existing, dict):
        existing["brands"] = brands
        existing["total"] = len(brands)
        BRANDS_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    else:
        BRANDS_JSON.write_text(json.dumps(brands, ensure_ascii=False, indent=2))

def collect(dry_run=False, filter_cat=None, force=False):
    existing_brands = load_brands()
    existing_ids = {b["id"] for b in existing_brands}
    today = date.today().isoformat()

    to_process = {
        bid: info for bid, info in BRANDS.items()
        if (filter_cat is None or info["category"] == filter_cat)
        and (force or bid not in existing_ids)
    }

    print(f"\n수집 대상: {len(to_process)}개 브랜드")
    if filter_cat:
        print(f"카테고리 필터: {filter_cat}")
    if dry_run:
        print("(dry-run 모드 — 실제 다운로드 없음)\n")

    added = []
    skipped = []
    failed = []

    for bid, info in to_process.items():
        brand_dir = LOGO_DIR / bid
        si_slug = info.get("simple_icon")
        domain = info.get("domain")
        cat = info["category"]

        print(f"\n[{bid}] {info['name_ko']} ({cat})")

        if bid in existing_ids and not force:
            print("  → 이미 존재, 건너뜀")
            skipped.append(bid)
            continue

        if dry_run:
            print(f"  → SVG: {si_slug_to_url(si_slug) if si_slug else '없음'}")
            print(f"  → PNG: {CLEARBIT.format(domain=domain) if domain else '없음'}")
            added.append(bid)
            continue

        brand_dir.mkdir(exist_ok=True)
        has_svg = False
        has_png = False

        # 1. Simple Icons SVG 다운로드
        if si_slug:
            svg_path = brand_dir / "logo.svg"
            url = si_slug_to_url(si_slug)
            print(f"  SVG: {url}")
            if download(url, svg_path):
                has_svg = True
                print(f"  ✓ SVG 저장 ({svg_path.stat().st_size} bytes)")
            else:
                # CDN 실패 시 raw GitHub 시도
                url2 = si_raw_url(si_slug)
                print(f"  SVG fallback: {url2}")
                if download(url2, svg_path):
                    has_svg = True
                    print(f"  ✓ SVG(raw) 저장")

        # 2. Clearbit PNG 다운로드
        if domain:
            png_path = brand_dir / "logo-800.png"
            url = CLEARBIT.format(domain=domain)
            print(f"  PNG: {url}")
            if download(url, png_path):
                has_png = True
                print(f"  ✓ PNG 저장 ({png_path.stat().st_size} bytes)")

        if not has_svg and not has_png:
            print(f"  ✗ 로고 없음 → 건너뜀")
            failed.append(bid)
            brand_dir.rmdir() if brand_dir.exists() and not any(brand_dir.iterdir()) else None
            continue

        # brands.json 엔트리 생성
        entry = {
            "id": bid,
            "name_ko": info["name_ko"],
            "name_en": info["name_en"],
            "category": cat,
            "folder": f"_clients/{bid}",
            "logo_svg": "logo.svg" if has_svg else None,
            "svg_source": "simple-icons" if si_slug and has_svg else None,
            "logo_png": has_png,
            "dark_variant": None,
            "sources": [],
            "added_at": today,
        }
        if domain:
            entry["domain"] = domain
            entry["website"] = domain

        if bid in existing_ids:
            # 기존 항목 업데이트
            existing_brands = [e if e["id"] != bid else entry for e in existing_brands]
        else:
            existing_brands.append(entry)
            existing_ids.add(bid)

        added.append(bid)
        time.sleep(0.3)  # 서버 부하 방지

    if not dry_run and added:
        save_brands(existing_brands)

    # 결과 요약
    print(f"\n{'='*50}")
    print(f"✅ 추가: {len(added)}개")
    print(f"⏭  건너뜀: {len(skipped)}개 (이미 존재)")
    print(f"❌ 실패: {len(failed)}개")
    if failed:
        print(f"   실패 목록: {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="글로벌 브랜드 로고 수집")
    parser.add_argument("--dry-run", action="store_true", help="다운로드 없이 목록만 확인")
    parser.add_argument("--cat", type=str, default=None, help="카테고리 필터 (예: AI·머신러닝)")
    parser.add_argument("--force", action="store_true", help="이미 있는 브랜드도 덮어쓰기")
    args = parser.parse_args()
    collect(dry_run=args.dry_run, filter_cat=args.cat, force=args.force)
