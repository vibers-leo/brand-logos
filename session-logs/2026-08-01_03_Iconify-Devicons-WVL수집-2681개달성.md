# 2026-08-01 (3차) — Iconify+Devicons+WorldVectorLogo 수집, 1,031 → 2,681개

## 세션 개요
- 프로젝트: brand-logos (logo.vibers.co.kr)
- 핵심 결과: 1,031개 → **2,681개** (+1,650개)
- 3개 오픈소스 로고 소스 파이프라인 구축 및 완료

## 주요 작업

### 1. Iconify logos 수집

Iconify API(`https://api.iconify.design/logos/{slug}.svg`)에서 logos 컬렉션 전체 수집.

**결과: 신규 1,357개 + 층위 추가 500개**

- `/collection?prefix=logos` API로 전체 아이콘 목록 취득
- 슬러그 suffix(`-icon`, `-wordmark`, `-color`, `-dark`, `-light`)로 변형 감지
- 기존 브랜드: `sources/iconify/{slug}.svg` 저장 + sources[] 레이어 추가
- 신규 브랜드: logo.svg + logo.png 생성 + DB 추가

### 2. Devicons 수집

`https://raw.githubusercontent.com/devicons/devicon/master/devicon.json`에서 578개 아이콘 수집.

**결과: 신규 263개 + 층위 추가 315개**

- "colored" > "original" > "plain" 변형 우선순위 적용
- `sources/devicons/{slug}-{variant}.svg` 저장
- 주요 추가: cplusplus, csharp, html5, css3, python, java, kotlin, swift 등 언어 아이콘

### 3. WorldVectorLogo 수집

`https://raw.githubusercontent.com/gilbarbara/logos/main/logos.json`에서 수집.

**결과: 신규 30개 + 층위 추가 1,815개**

- GitHub contents API(rate limit 403) 대신 raw.githubusercontent.com logos.json 직접 파싱
- `logos.json` 형식: `{"name", "shortname", "files": ["adobe.svg", "adobe-icon.svg"]}`
- `sources/wvl/{fname}.svg` 저장
- WVL은 Iconify와 거의 동일한 로고 세트 → 대부분 기존 브랜드에 층위 추가
- 기술/개발 브랜드에 아이콘/워드마크 2-3개 변형 추가

## 기술적 상세

### 최종 DB 현황
| 항목 | 값 |
|------|-----|
| 총 브랜드 | 2,681개 |
| 2개 이상 sources | 1,401개 |
| sources 없음 | 22개 (소규모 한국 브랜드) |

### collect-auto.py 추가 함수
| 함수 | CLI | 소스 |
|------|-----|------|
| `collect_iconify()` | `--source iconify` | api.iconify.design |
| `collect_devicons()` | `--source devicons` | raw.githubusercontent.com/devicons |
| `collect_worldvector()` | `--source worldvector` | raw.githubusercontent.com/gilbarbara/logos |

### sources 파일 경로 구조
```
_clients/{brand-id}/
├── logo.svg          # 대표 로고 (최초 수집 or 가장 고품질)
├── logo.png          # 400×400 PNG
├── sources/
│   ├── fa.svg        # Font Awesome
│   ├── si.svg        # Simple Icons
│   ├── iconify/      # Iconify logos 변형들
│   │   ├── {brand}.svg
│   │   └── {brand}-icon.svg
│   ├── devicons/     # Devicons
│   │   └── {brand}-original.svg
│   └── wvl/          # WorldVectorLogo
│       ├── {brand}.svg
│       └── {brand}-icon.svg
```

### 변경 파일
| 파일 | 변경 내용 |
|------|---------|
| `collect-auto.py` | collect_iconify/devicons/worldvector 함수 추가 |
| `_clients/brands.json` | 2,681개 브랜드, 전체 sources 업데이트 |
| `_clients/*/` | 신규 1,650개 + 기존 브랜드 sources/ 폴더 추가 |

## 향후 계획
- 버전 비교 UI에서 1,401개 멀티소스 브랜드 탐색 지원 강화
- logo_quality 필드 신규 브랜드에도 일괄 적용 (현재 SVG 기반이라 ok 처리)
- 한국 브랜드 로고 추가 수집 (현재 주로 글로벌/테크 브랜드 위주)
- dark_variant 필드 신규 브랜드 일괄 적용
