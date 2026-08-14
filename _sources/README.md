# 로고 원본 보관소

브랜드가 준 **원본 파일**(.ai / .eps / CI 패키지)을 브랜드 id 이름으로 둔다.
변환 결과(`_clients/{id}/logo.svg`)와 달리 이건 다시 만들 수 없는 자산이다.

## git 이 추적하지 않는다
`.git` 이 이미 626MB 라 원본까지 넣으면 clone 이 무거워진다.
대신 여기 두고, 백업은 드라이브·외장으로 한다.

## 쓰는 법
```bash
python3 scripts/ai-to-svg.py _sources/{id}.ai -o _clients/{id}/logo.svg
```
`.ai` 는 PDF 호환이면 그대로 변환되고, 아주 오래된 EPS 기반이면
Illustrator 에서 다시 저장해야 한다. 자세한 건 `scripts/ai-to-svg.py` 주석 참고.

## 목록
| 파일 | 브랜드 | 출처 |
|---|---|---|
| `atomy.ai` | 애터미 | 공식 CI (Atomy+CI.zip 에서 추출) |
| `daehan-shipbuilding.ai` | 대한조선 | 공식 CI |
| `hd-korea-shipbuilding.ai` | HD한국조선해양 | 공식 CI |
| `ibk.ai` | IBK기업은행 | 공식 CI |
| `sbmarine/에스비마린로고.eps` | 에스비마린 | 공식 CI (국문 시그니처, 그라데이션) |
| `sbmarine/SB_영문만로고.ai` | 에스비마린 | 공식 CI (영문, 단색 1도) |

위쪽 4개는 PDF 호환 `.ai` 라 `ai-to-svg.py` 로 바로 변환된다 (2026-08-13 확인).

## ⚠️ 변환이 안 되는 두 가지 (2026-08-14 에스비마린에서 겪음)

**① 진짜 EPS 는 Inkscape 가 직접 못 읽는다.** ghostscript 를 거치면 된다:
```bash
ps2pdf -dEPSCrop 원본.eps out.pdf && pdftocairo -svg out.pdf out.svg
```
국문 로고는 이 경로로 그라데이션까지 온전히 벡터 변환됐다 (path 32개).

**② sK1 로 내보낸 `.ai` 는 ghostscript 도 못 읽는다** (`/undefined in XR`).
확장자만 `.ai` 지 내용은 Illustrator 고유 연산자(`XR`·`Lb`·`k`·`C`)를 쓰는
PostScript 이고, 그 연산자를 정의하는 prolog 가 빠져 있다.
연산자가 몇 개 안 되면(`m`·`L`·`C`·`f`·`k`) 직접 파싱하는 게 빠르다.

이때 **`*u`…`*U` 컴파운드 패스 그룹을 반드시 지켜야 한다.** 무시하고 전부
한 패스로 합치면 글자 속 구멍이 메워져 마크가 뭉갠 덩어리가 된다.

## svgo 는 그라데이션을 깨뜨릴 수 있다
`preset-default` 를 돌렸더니 SB 마크의 블루 그라데이션이 눈에 띄게 바뀌었다
(평균 픽셀차 2.4). 플러그인을 골라 꺼도 마찬가지였다.
**최적화 후에는 반드시 원본과 픽셀 대조**하고, 다르면 쓰지 않는다.
