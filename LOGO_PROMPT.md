# 브랜드 로고 DB — 공통 프롬프트

## 로고 DB 위치
```
~/Desktop/macminim4/brand-logos/
├── _clients/          ← Vibers 클라이언트 브랜드 (현대, 삼성, LG 등 대형사)
│   ├── brands.json    ← 인덱스 DB (브랜드명, 카테고리, 도메인, 파일 정보)
│   └── {brand-id}/
│       ├── logo.svg   ← 벡터 (우선 사용)
│       └── logo.png   ← 래스터 400px
├── validate-logos.sh  ← 로고 품질 검증 스크립트
├── yahwa/             ← Vibers 자체 브랜드
├── oluolu/
└── ...
```

---

## ⚠️ SVG 품질 규칙 (반드시 읽을 것)

로고를 추가하기 전 반드시 아래 조건을 확인한다. **하나라도 위반하면 사용 불가.**

| 조건 | 확인 방법 |
|------|---------|
| 진짜 벡터 SVG (`<svg` 태그 있음) | `grep -c '<svg' file.svg` → 1 이상 |
| 비트맵 내장 없음 | `grep -c 'data:image/' file.svg` → 0 |
| `<image` 태그 없음 | `grep -c '<image' file.svg` → 0 |
| HTML 에러페이지 아님 | `head -1 file.svg` → `<svg` 또는 `<?xml` 으로 시작 |
| 파일 크기 적정 | 순수 벡터는 보통 1~20KB. 50KB 초과 시 직접 확인 필요 (단, Adobe Illustrator 생성 복잡 SVG는 100KB 가능) |
| 배경 투명 | 어두운 배경에서 흰 사각형으로 보이면 사용 불가 |

### 빠른 검증 명령어 (1줄)
```bash
python3 -c "
with open('logo.svg','rb') as f: c=f.read()
ok = b'<svg' in c and b'data:image/' not in c and b'<image' not in c and b'DOCTYPE html' not in c
print('✅ 벡터 SVG' if ok else '❌ 사용 불가 — 비트맵 내장 또는 불량 파일')
"
```

### DB 전체 검증
```bash
python3 ~/Desktop/macminim4/brand-logos/validate-logos.sh
```

---

## 로고 소스 우선순위

1. **위키미디어 Commons** ← 한국 대기업·공공기관·아이돌 그룹에 강함. 항상 먼저 확인
   - Wikipedia 파일 페이지: `https://ko.wikipedia.org/wiki/파일:{파일명}.svg`
   - 수집 스크립트: `python3 ~/Desktop/macminim4/brand-logos/wiki-fetch.py --brand {id} --url {위키URL}`
   - 주의: UTF-16 인코딩 파일이 있음 → 스크립트가 자동 변환함

2. **Brandfetch API** ← 글로벌 기업·IT 기업에 강함. 공식 브랜드 에셋
   - API 키: `$BRANDFETCH_API_KEY` (~/.secrets에 있음)
   - 명령어: `curl -s "https://api.brandfetch.io/v2/brands/{domain}" -H "Authorization: Bearer $BRANDFETCH_API_KEY"`
   - **반드시 SVG format 확인 후 다운로드** (PNG만 있으면 2번으로)

2. **Simple Icons** ← 기술/글로벌 브랜드 단색 SVG. CDN에서 즉시 다운
   - `curl -sL "https://cdn.simpleicons.org/{slug}" -o logo.svg`
   - 단색(검정) SVG → 어두운 배경에서 `mono: true`로 흰색 반전 필요

3. **Worldvectorlogo** ← 한국 대기업, 오래된 브랜드
   - `curl -sL "https://cdn.worldvectorlogo.com/logos/{slug}.svg" -o logo.svg`

4. **공식 홈페이지 Press Kit** ← 위 3개 모두 없으면 직접 찾기
   - 브랜드 공식 사이트 → Newsroom / Press / Brand Assets 메뉴

5. ❌ **Inkscape PNG→SVG 변환 금지** — 비트맵이 SVG에 내장되어 배경이 흰색으로 나옴

---

## A. 다른 프로젝트에서 로고 가져올 때

### 1. DB에서 검색
```bash
cat ~/Desktop/macminim4/brand-logos/_clients/brands.json | python3 -c "
import json,sys
db = json.load(sys.stdin)
for b in db['brands']:
    print(b['id'], '|', b['name_ko'], '|', b['category'])
"
```

### 2. 로고 파일 복사
```bash
# SVG 우선, 없으면 PNG
BRAND=hyundai
PROJECT_DIR=~/Desktop/macminim4/dev/nextjs/apps/{프로젝트명}/public/logos

cp ~/Desktop/macminim4/brand-logos/_clients/$BRAND/logo.svg $PROJECT_DIR/$BRAND.svg
```

### 3. DB에 없는 브랜드 — Brandfetch로 즉석 다운로드
```bash
source ~/.secrets
DOMAIN=example.com
BRAND=brand-id

mkdir -p ~/Desktop/macminim4/brand-logos/_clients/$BRAND

# SVG URL 가져오기
SVG_URL=$(curl -s "https://api.brandfetch.io/v2/brands/$DOMAIN" \
  -H "Authorization: Bearer $BRANDFETCH_API_KEY" | python3 -c "
import sys,json; d=json.load(sys.stdin)
for logo in d.get('logos',[]):
    for fmt in logo.get('formats',[]):
        if fmt.get('format')=='svg' and logo.get('type')=='logo':
            print(fmt.get('src',''))
            break
")

# 다운로드 + 즉시 검증
curl -sL "$SVG_URL" -H "Authorization: Bearer $BRANDFETCH_API_KEY" -o /tmp/logo_test.svg
python3 -c "
with open('/tmp/logo_test.svg','rb') as f: c=f.read()
ok = b'<svg' in c and b'data:image/' not in c and b'<image' not in c
print('✅ 사용 가능' if ok else '❌ 비트맵 내장 — 다른 소스 필요')
"
# 검증 통과 시에만 복사
cp /tmp/logo_test.svg ~/Desktop/macminim4/brand-logos/_clients/$BRAND/logo.svg
```

### 4. logo.dev API (PNG 전용, SVG 불가)
```bash
TOKEN=pk_PMYAJ8oDRDG9VWZU6uPH6w
curl -s "https://img.logo.dev/{domain}?token=$TOKEN&format=png&size=400" -o logo.png
```

---

## B. 새 로고를 DB에 추가할 때

> 추가 기준: Vibers 클라이언트 브랜드 / 자주 쓰이는 브랜드 / 자체 제작 로고

### 추가 절차
```bash
BRAND=brand-id
BASE=~/Desktop/macminim4/brand-logos/_clients

# 1. 폴더 + 파일 저장 (위 소스 우선순위 참고)
mkdir -p $BASE/$BRAND
cp /path/to/logo.svg $BASE/$BRAND/logo.svg

# 2. SVG 내재화 (불필요한 메타데이터 제거, 표준 포맷 정규화)
python3 ~/Desktop/macminim4/brand-logos/internalize-svg.py --brand $BRAND

# 3. 변형 생성 (800px PNG, 아이콘, 투명, 흰색 버전)
python3 ~/Desktop/macminim4/brand-logos/build-variants.py --brand $BRAND

# 4. NCP vibers-bucket 업로드 (필수 — 재배포 무관 영구 보관)
cd ~/Desktop/macminim4/brand-logos && source ~/.secrets && python3 upload-to-bucket.py --brand $BRAND
# 버킷 URL: https://kr.object.ncloudstorage.com/vibers-bucket/brand-logos/{id}/{file}

# 5. GitHub Pages CDN 반영 (logo.vibers.co.kr)
git -C ~/Desktop/macminim4/brand-logos add _clients/$BRAND/ _clients/brands.json && git -C ~/Desktop/macminim4/brand-logos commit -m "feat: $BRAND 로고 추가" && git -C ~/Desktop/macminim4/brand-logos push

# ⚠️ 배포 대기 중 폴링은 반드시 무작위 파라미터로 한다 (2026-08-14 사고)
#   ❌ curl ".../variants.json?v=$NEW_VERSION"   ← 확인 행위가 옛 응답을 그 URL에 캐시로 박는다
#   ✅ curl ".../variants.json?probe=$RANDOM"
# CF 캐시 규칙의 엣지 TTL(1시간)이 오리진 max-age=600 을 덮어쓴다. 한 번 오염되면
# 퍼지 권한이 없어(현재 토큰) 1시간을 기다리거나 VERSION 을 새로 올려야 한다.

# 6. 검증
python3 ~/Desktop/macminim4/brand-logos/validate-logos.sh

# 7. brands.json 업데이트
python3 << EOF
import json
with open('$BASE/brands.json', encoding='utf-8') as f:
    db = json.load(f)
db['brands'].append({
    "id": "$BRAND",
    "name_ko": "한글명",
    "name_en": "English Name",
    "category": "카테고리",
    "domain": "example.com",
    "logo_svg": True,
    "logo_png": False,
    "svg_source": "brandfetch"   # brandfetch / simple-icons / worldvectorlogo / official
})
db['total'] = len(db['brands'])
with open('$BASE/brands.json', 'w', encoding='utf-8') as f:
    json.dump(db, f, ensure_ascii=False, indent=2)
print("추가 완료:", "$BRAND")
EOF
```

### `mono` 플래그 설정 기준 (베데라인 등 어두운 배경 프로젝트)
| 로고 종류 | mono 값 |
|----------|---------|
| 단색(검정/흰) 원본 → 어두운 배경에서 보이려면 반전 필요 | `mono: true` |
| 컬러 로고 (빨강, 파랑, 초록 등) | `mono: false` 또는 생략 |
| Brandfetch dark 테마로 받은 로고 | 이미 밝은 색이므로 `mono: false` |
| Simple Icons CDN (단색 검정) | `mono: true` |

---

## C. 현재 수록 브랜드 (2026-07-29 기준)

### ✅ 사용 가능 (벡터 SVG)
| 브랜드 | ID | 소스 |
|--------|-----|------|
| 현대자동차 | hyundai | Simple Icons |
| 현대건설 | hyundai-construction | Simple Icons (현대 동일 로고) |
| 기아 | kia | Simple Icons |
| 스타벅스 | starbucks | Simple Icons |
| 삼성전자 | samsung-bespoke | Simple Icons |
| 삼성전자 | samsung-mobile | Simple Icons (동일 파일) |
| 삼성물산 | samsung-ct | Brandfetch |
| 삼성SDS | samsung-sds | Brandfetch |
| LG전자 | lg-electronics | Simple Icons |
| LG에너지솔루션 | lg-energy-solution | Brandfetch |
| SK그룹 | sk | Brandfetch |
| SK텔레콤 | sk-telecom | Brandfetch (99KB, AI 복잡 벡터) |
| 로얄캐닌 | royal-canin | Brandfetch |
| 필로소피 | philosophy | Brandfetch |
| 페레로로쉐 | ferrero-rocher | Brandfetch |
| 대림건설(DL E&C) | daelim | Brandfetch |
| 한국수력원자력 | khnp | Brandfetch |
| 제일기획 | cheil | Brandfetch |
| HYBE | hybe | Brandfetch |

### ❌ 아직 확보 못 한 브랜드
| 브랜드 | 이유 |
|--------|------|
| 오뚜기 | 모든 소스 비트맵만 존재 |
| 젤리캣 | 모든 소스 비트맵만 존재 |
| HiKR GROUND | 2021 신생 브랜드, 공식 SVG 없음 (현재 HYBE 로고로 대체 중) |

---

## D. Brandfetch 사용량 관리

- 무료 플랜: **월 500 requests**
- API 키: `$BRANDFETCH_API_KEY` (~/.secrets)
- 1 브랜드 조회 = 1 request (로고 다운로드는 CDN이라 별도 카운트 안 됨)
- 잔여량 확인: Brandfetch 대시보드 (brandfetch.com/dev)
- **새 브랜드 추가 시에만 API 호출** (기존 브랜드 재확인 불필요)
