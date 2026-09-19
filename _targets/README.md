# 수집 요청 큐

사용자가 전달한 이름 목록은 `create-logo-request-queue.py`로 `_targets/*.json`에 저장합니다.

```bash
python3 scripts/create-logo-request-queue.py --input names.txt --output _targets/request-queue.json
node scripts/collect-site-svg.mjs --input _targets/request-queue.json
```

`needs_official_url` 항목은 공식 홈페이지 확인 전까지 자동 수집하지 않습니다. `user_provided`는 제공 파일을 원본·투명 배경·벡터 여부로 검수한 뒤 별도로 반영하고, `pending_delivery`는 파일을 받은 뒤 처리합니다.
