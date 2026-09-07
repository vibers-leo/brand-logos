#!/usr/bin/env python3
"""_clients/brands.json 을 커밋 직전에 **한 줄(compact)** 로 정규화한다.

스크립트마다 indent=1 / indent=2 / compact 가 섞여 있어 마지막에 쓴 쪽의 포맷이 이긴다.
그 결과 세션(한 줄) ↔ 크론(들여쓰기)이 번갈아 바뀌며 **커밋마다 120만 줄 diff** 가 났다(2026-09-07).
내용은 건드리지 않는다 — 파싱 후 그대로 다시 쓴다. 이미 한 줄이면 아무것도 안 한다.
크론 '변형 산출물 커밋' 단계와 rebase-push.sh 가 부른다.
"""
import json, sys
from pathlib import Path
p = Path(__file__).resolve().parent.parent / "_clients" / "brands.json"
raw = p.read_text()
if raw.count("\n") <= 1:
    print("brands.json 이미 한 줄"); sys.exit(0)
data = json.loads(raw)
p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
print(f"✅ brands.json 한 줄로 정규화 ({raw.count(chr(10)):,}줄 → 1줄)")
