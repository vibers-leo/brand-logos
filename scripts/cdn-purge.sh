#!/bin/bash
# logo.vibers.co.kr 엣지 캐시 퍼지 — 글로벌 API 키(보안.env) 사용. 2026-09-07 부터 가능해졌다.
#   bash scripts/cdn-purge.sh https://logo.vibers.co.kr/_clients/{id}/logo.png?v=...   (URL 여러 개, 쿼리까지 정확히)
#   bash scripts/cdn-purge.sh --brand bwcac                                            (그 브랜드 파일 전부, 현재 VERSION 키로)
#   bash scripts/cdn-purge.sh --all                                                    (존 전체 — 최후 수단)
# 왜: 워커/캐시 룰이 404 도 캐시해 신규 로고가 옛 ?v= 키에서 30일 안 보이던 사고. 룰에 404=60초를 넣었지만 이미 굳은 건 퍼지해야 한다.
set -euo pipefail
F=~/Desktop/macminim4/.secrets/보안.env
EM=$(grep -oE '^CLOUDFLARE_ACCOUNT_EMAIL=\S+' "$F" | cut -d= -f2); GK=$(grep -oE '^CLOUDFLARE_GLOBAL_API_KEY=\S+' "$F" | cut -d= -f2)
Z=e3fd3fc7ce63194b49cac1df365df6e7   # vibers.co.kr
H=(-H "X-Auth-Email: $EM" -H "X-Auth-Key: $GK" -H "Content-Type: application/json")
if [[ "${1:-}" == "--all" ]]; then BODY='{"purge_everything":true}'
elif [[ "${1:-}" == "--brand" ]]; then
  V=$(grep -oE 'VERSION = "[0-9]+"' /Volumes/Untitled/dev/nextjs-apps/semologo/src/lib/cdn.ts | grep -oE '[0-9]+')
  BODY=$(python3 -c "import json,sys; b=sys.argv[1]; v=sys.argv[2]; fs=['logo.svg','logo.png','logo-800.png','logo-icon.png','logo-transparent.png','logo-white.png','brand.json','variants.json']; print(json.dumps({'files':[f'https://logo.vibers.co.kr/_clients/{b}/{f}?v={v}' for f in fs]+[f'https://logo.vibers.co.kr/_clients/{b}/{f}' for f in fs]}))" "$2" "$V")
else BODY=$(python3 -c 'import json,sys; print(json.dumps({"files":sys.argv[1:]}))' "$@"); fi
curl -s -X POST "${H[@]}" "https://api.cloudflare.com/client/v4/zones/$Z/purge_cache" --data "$BODY" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("✅ 퍼지 완료" if d.get("success") else "❌ "+str([e["message"] for e in d.get("errors",[])]))'
