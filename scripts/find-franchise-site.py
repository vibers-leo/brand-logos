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


# 여러 브랜드에 같은 도메인이 제안되면 그건 **집계·포털 사이트**다.
# 스니펫 검증만으로는 이걸 못 가른다 — 포털은 브랜드 이름을 진짜로 적어놓기
# 때문이다. 실측(표본 14건): daangn.com 3회 · tabling.co.kr · kfood.kr ·
# myfranchise.kr · pandarank.net 이 전부 '확인'을 통과했다. 전부 오답이다.
# DENY 목록을 손으로 채우면 계속 새므로 **빈도로 자동 발견**한다.
# 배치 안에서 서로 다른 브랜드 이만큼에 제안되면 집계 사이트로 본다.
# 2 로 잡는 이유 — 프랜차이즈 본사가 한 사이트에 여러 브랜드를 두는 경우가
# 있긴 하지만(한솔교육 지사 4개), 그건 어차피 같은 로고라 뒤에서 중복으로
# 걸린다. 집계 사이트를 놓치는 쪽이 훨씬 비싸다.
AGG_MIN = 2
AGG_FILE = TARGETS.parent / "aggregators.json"


def _load_agg() -> set:
    if AGG_FILE.exists():
        return set(json.loads(AGG_FILE.read_text()))
    return set()


def _save_agg(s: set) -> None:
    AGG_FILE.write_text(json.dumps(sorted(s), ensure_ascii=False, indent=1) + "\n")


def find(row):
    """(url, 경로, 도메인) 또는 (None, None, None)"""
    for q, tag in ((row["brand"], "브랜드"), (row.get("hq", ""), "본사")):
        if not q:
            continue
        try:
            items = _fos.search(q)
        except Exception:
            continue
        for dom, n in _fos.candidates(items):
            # 스니펫에서 이름이 확인되면 페이지는 **접속만** 되면 채택한다.
            # (JS 로 그리는 사이트는 raw HTML 에 이름이 없다 — 아래 주석 참조)
            # ⚠️ **스니펫 매칭을 신뢰하면 안 된다.** 2026-09-03 에
            #    `snippet_ok` 로 완화했더니 적중률이 1%→93% 로 뛰었는데
            #    **전부 오답**이었다 — daangn.com·ridibooks.com·
            #    encykorea.aks.ac.kr·opengov.seoul.go.kr 이 채택됐다.
            #    포털은 브랜드 이름을 진짜로 적어놓기 때문에 스니펫만으로는
            #    '소유한 사이트'와 '언급한 사이트'를 못 가른다.
            #    **페이지 본문에서 이름이 확인될 때만** 채택한다.
            url, why = _fos.verify(dom, row["brand"])
            if url and why == "확인":
                return url, tag, dom
        time.sleep(0.2)
    return None, None, None


def main():
    apply_ = "--apply" in sys.argv
    rows = json.loads(TARGETS.read_text())
    todo = [r for r in rows if not (r.get("site") or "").strip()]
    limit = (len(todo) if "--all" in sys.argv else
             int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 100)
    todo = todo[:limit]
    print(f"  홈페이지 없음 {len(rows)-sum(1 for r in rows if r.get('site')):,} · 이번 {len(todo):,}", flush=True)

    # ── 1패스: 제안만 모은다 (저장하지 않는다) ──────────────────────
    # ⚠️ 여기서 바로 저장하면 **집계 사이트를 브랜드 홈페이지로 박아버린다.**
    #    실측(표본 80): 제안 71건 중 49건이 반복 도메인이었다 —
    #    daangn.com 7회 · fclh.purpleo.co.kr 6회 · polle.com 4회 …
    #    한 브랜드만 보면 '이름이 페이지에 있으니 맞다'로 보인다.
    #    여러 브랜드를 **함께 봐야** 집계 사이트가 드러난다.
    prop = []
    for i, r in enumerate(todo, 1):
        url, tag, dom = find(r)
        if url:
            prop.append((r, url, tag, dom))
        if i % 50 == 0:
            print(f"   {i:,}/{len(todo):,} · 제안 {len(prop):,}", flush=True)
        time.sleep(0.2)

    # ── 2패스: 여러 브랜드에 걸친 도메인을 걷어낸다 ──────────────────
    by_dom = {}
    for r, url, tag, dom in prop:
        by_dom.setdefault(dom, []).append(r["brand"])
    agg = {d for d, bs in by_dom.items() if len(set(bs)) >= AGG_MIN}
    known = _load_agg()
    agg |= {d for d in by_dom if d in known}

    found = 0
    for r, url, tag, dom in prop:
        if dom in agg:
            continue
        r["site"] = url
        r["site_source"] = f"naver-{tag}"
        found += 1

    print(f"\n  제안 {len(prop):,} → 집계 사이트 {len(agg)}곳 제외 → 채택 {found:,} / {len(todo):,}")
    if agg:
        print("  집계 사이트:", ", ".join(sorted(agg)[:8]) + (" …" if len(agg) > 8 else ""))
    if apply_:
        TARGETS.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
        _save_agg(known | agg)
        print("  ✅ _targets/franchise.json 갱신")


if __name__ == "__main__":
    main()
