#!/usr/bin/env bash
# 수집 반영 이후의 후속 단계를 순서대로 돌린다.
#
# 왜 스크립트인가 — `--apply` 는 **logo.svg 만 복사한다.** PNG 도 변형도
# 안 만든다. 그래서 여기 있는 단계를 빠뜨리면 신규 브랜드 전부가
#   · PNG 다운로드 404 (logo.png 가 없다)
#   · 다크 카드 오판 (light_logo 미갱신)
#   · 목록에 안 보임 (slim 미갱신)
# 이 된다. 실제로 2026-08-16 에 신규 231개가 PNG 404 였다.
#
# 순서가 중요하다:
#   ensure-logo-png → build-variants → 매니페스트 → 밝기판정 → slim → 검사 → 업로드
#   PNG 를 만들기 전에 버킷에 올리면 올릴 게 없고, 검사 전에 올리면
#   깨진 파일이 CDN 에 박힌다.
#
#   bash scripts/finish-collect.sh          # 전부
#   bash scripts/finish-collect.sh --no-upload   # 버킷 업로드만 생략
set -euo pipefail
cd "$(dirname "$0")/.."

UPLOAD=1
[ "${1:-}" = "--no-upload" ] && UPLOAD=0

step() { printf '\n\033[1m── %s\033[0m\n' "$1"; }

step "1/7 logo.png 보정 + 가짜 벡터 정리"
# ensure-logo-png 는 **일부 실패가 있으면 exit 1** 을 낸다(빈 렌더·시간초과 등).
# 그건 "이 브랜드는 PNG 없이 SVG 만 서비스" 라는 정상 처리지 치명적 오류가
# 아니다. set -e 로 여기서 멈추면 뒤 6단계가 통째로 안 돈다 —
# 실제로 2026-08-18 에 실패 170건 때문에 파이프라인이 1단계에서 끊겼다.
# 다만 조용히 넘기지는 않는다: 종료코드가 1 이 아니면(크래시) 중단한다.
set +e
python3 scripts/ensure-logo-png.py --demote-fake
rc=$?
set -e
if [ "$rc" -gt 1 ]; then
  echo "❌ 1단계가 비정상 종료했다 (exit $rc) — 중단한다"
  exit "$rc"
fi
[ "$rc" = "1" ] && echo "⚠️ 일부 PNG 생성 실패 (위 목록) — 나머지 단계는 계속한다"

step "2/7 PNG 파생물 생성 (logo-800·icon·transparent·white)"
python3 build-variants.py

step "3/7 변형 매니페스트"
python3 scripts/build-logo-variants.py

step "4/7 밝은 로고 판정 (어두운 카드로 그릴 대상)"
python3 scripts/scan-light-logos.py

step "5/7 brands-slim 재생성"
python3 scripts/build-slim.py
python3 scripts/build-slim.py --check

step "6/7 에셋 무결성 검사"
python3 scripts/check-assets.py

if [ "$UPLOAD" = "1" ]; then
  step "7/7 PNG 버킷 업로드"
  if [ -z "${NCP_ACCESS_KEY:-}" ]; then
    echo "❌ NCP 키가 없다 — source ~/Desktop/macminim4/.secrets/보안.env 후 다시 실행"
    echo "   업로드를 건너뛰면 신규 브랜드의 PNG 다운로드가 404 다."
    exit 1
  fi
  python3 scripts/sync-png-bucket.py --workers 24 --verify 40
else
  step "7/7 버킷 업로드 — 생략됨"
  echo "⚠️ 업로드 전까지 신규 브랜드의 PNG 는 CDN 에서 404 다."
fi

printf '\n✅ 후속 단계 완료. 남은 일: VERSION 동기화 → 커밋·푸시 → Pages 배포 확인\n'
