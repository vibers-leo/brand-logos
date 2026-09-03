#!/usr/bin/env python3
"""카테고리별 '같은 분야 브랜드' 목록을 작은 파일 하나로 낸다.

상세 페이지는 연관 브랜드 12개를 보여주려고 `brands-slim.json`(12.9MB)을
통째로 받고 있었다. 빌드 워커 9개가 각자 파싱하면서 힙이 터져
**배포가 실패했다.** 필요한 건 카테고리당 12개뿐이다.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import atomic_json

C = Path(__file__).resolve().parent.parent / "_clients"
PER = 24        # 12개만 쓰지만 여유를 둔다 (숨김·변형이 섞여도 채워지게)

raw = json.loads((C / "brands.json").read_text())
br = raw["brands"] if isinstance(raw, dict) else raw

# 인지도 높은 것부터 담는다 — 연관 추천이 무명 브랜드로 채워지지 않게
br = sorted(br, key=lambda b: -(b.get("fame") or 0))

out: dict[str, list] = {}
for b in br:
    if b.get("hidden") or b.get("variant_of"):
        continue
    cat = b.get("category") or "기타"
    lst = out.setdefault(cat, [])
    if len(lst) >= PER:
        continue
    lst.append({"id": b["id"], "name_ko": b.get("name_ko"),
                "name_en": b.get("name_en"), "category": cat,
                "has_svg": bool(b.get("has_svg")), "has_png": bool(b.get("has_png"))})

p = C / "category-peers.json"
atomic_json.write_json(p, out)
print(f"✅ category-peers.json — 카테고리 {len(out)}개 · {p.stat().st_size/1024:.0f}KB")
