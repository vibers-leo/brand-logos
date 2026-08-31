#!/usr/bin/env python3
"""같은 이미지 파일을 쓰는 브랜드를 찾는다 — '잘못 올라간 것'의 가장 강한 신호.

로고답지 않은 이미지를 찾는 판정기들(잉크·알파·문장)은 오탐이 지배적이었다.
국기는 잉크가 100%라 전부 '통짜배너'로 걸리고, 한글 워드마크는 전부
'문장이미지'로 걸린다.

그런데 **두 브랜드가 바이트까지 같은 이미지를 쓰고 있다면** 하나는
반드시 틀렸다. 판정이 아니라 사실이다.

  python3 scripts/find-duplicate-logos.py
"""
import hashlib, json, os
from collections import defaultdict

d = json.load(open("_clients/brands.json"))["brands"]
name = {b["id"]: (b.get("name_ko") or b.get("name_en"), b.get("category")) for b in d}
groups = defaultdict(list)
n = 0
for b in d:
    if b.get("hidden"): continue
    base = f"_clients/{b['id']}"
    for f in ("logo.svg", "logo.png"):
        p = f"{base}/{f}"
        if not os.path.exists(p): continue
        h = hashlib.sha1(open(p, "rb").read()).hexdigest()[:16]
        groups[(f, h)].append(b["id"]); n += 1
        break
dups = {k: v for k, v in groups.items() if len(v) > 1}
tot = sum(len(v) for v in dups.values())
print(f"  검사 {n:,}개 · 중복 그룹 {len(dups)}개 · 관련 브랜드 {tot}개")
big = sorted(dups.items(), key=lambda x: -len(x[1]))
for (f, h), ids in big[:25]:
    row = " · ".join(f"{i}({name.get(i,('?',))[0]})" for i in ids[:5])
    more = f" +{len(ids)-5}" if len(ids) > 5 else ""
    print(f"   [{len(ids)}] {row}{more}")
json.dump({f"{k[0]}:{k[1]}": v for k, v in dups.items()},
          open("/tmp/dup-logos.json", "w"), ensure_ascii=False)
