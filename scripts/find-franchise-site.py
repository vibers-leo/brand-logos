#!/usr/bin/env python3
"""프랜차이즈 브랜드의 공식 홈페이지를 찾는다.

공정위 정보공개서 명단(11,846건)에는 **홈페이지가 없다.** 그래서 2026-08-29
수집이 실패했다 — 검색 1등을 그대로 믿어 창업뉴스·위키가 들어왔다.

find-official-site.py 의 검증 방식을 그대로 쓴다:
검색 → 차단 목록 → **실제 접속해 브랜드명 확인**. 이름이 확인된 것만 채택한다.

브랜드명으로 못 찾으면 본사명으로 한 번 더 본다 — 본사 사이트에 브랜드
소개가 있는 경우가 많다(놀부 한 곳이 33개 브랜드를 갖는다).

실측 성공률 36%. 11,846건 기준 약 4,200개를 건질 수 있다.

  python3 scripts/find-franchise-site.py --limit 100
  python3 scripts/find-franchise-site.py --all --apply
"""
import importlib.util as il
import json, os, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TARGETS = BASE / "_targets" / "franchise.json"

_spec = il.spec_from_file_location("fos", Path(__file__).resolve().parent / "find-official-site.py")
_fos = il.module_from_spec(_spec)
_a = sys.argv
sys.argv = ["x", "--limit", "0"]
try:
    _spec.loader.exec_module(_fos)
finally:
    sys.argv = _a


def find(row):
    """(url, 경로) 또는 (None, None)"""
    for q, tag in ((row["brand"], "브랜드"), (row.get("hq", ""), "본사")):
        if not q:
            continue
        try:
            items = _fos.search(q)
        except Exception:
            continue
        for dom, n in _fos.candidates(items):
            url, why = _fos.verify(dom, row["brand"])
            if url and why == "확인":
                return url, tag
        time.sleep(0.2)
    return None, None


def main():
    apply_ = "--apply" in sys.argv
    rows = json.loads(TARGETS.read_text())
    todo = [r for r in rows if not (r.get("site") or "").strip()]
    limit = (len(todo) if "--all" in sys.argv else
             int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 100)
    print(f"  홈페이지 없음 {len(todo):,} · 이번 {min(limit,len(todo)):,}", flush=True)
    found = 0
    for i, r in enumerate(todo[:limit], 1):
        url, tag = find(r)
        if url:
            r["site"] = url
            r["site_source"] = f"naver-{tag}"
            found += 1
        if i % 50 == 0:
            print(f"   {i:,}/{min(limit,len(todo)):,} · 찾음 {found:,}", flush=True)
            if apply_:
                TARGETS.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
        time.sleep(0.2)
    print(f"\n  찾음 {found:,} / {min(limit,len(todo)):,}")
    if apply_:
        TARGETS.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
        print("  ✅ _targets/franchise.json 갱신")

main()
