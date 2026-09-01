#!/bin/bash
# 버킷 동기화 — **PNG 와 그 외를 둘 다** 올린다.
#
# ⚠️ 스크립트가 둘로 갈려 있고 이름이 헷갈린다:
#     sync-png-bucket.py   PNG 만
#     sync-all-bucket.py   PNG **외**(SVG·JSON) — 이름과 달리 전부가 아니다
#   2026-09-01 에 sync-all 만 돌리고 "업로드 452개 완료"를 보고 끝낸 줄 알았는데,
#   방금 복구한 파생 PNG 1,878개가 통째로 빠져 CDN 이 404 를 냈다.
#   같은 실수를 이 세션에서 두 번 했다. 이제 이 스크립트 하나만 쓴다.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
source ~/Desktop/macminim4/.secrets/보안.env 2>/dev/null || {
  echo "⛔ .secrets 를 읽을 수 없다"; exit 1; }

rc=0
for s in sync-png-bucket sync-all-bucket; do
  echo "▶ $s"
  python3 "scripts/$s.py" --workers "${WORKERS:-32}" "$@" || rc=1
done
[ $rc -ne 0 ] && echo "⛔ 일부 실패 — 위 로그 확인"
exit $rc
