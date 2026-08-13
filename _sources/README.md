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

전부 PDF 호환 `.ai` 라 `ai-to-svg.py` 로 바로 변환된다 (2026-08-13 확인).
