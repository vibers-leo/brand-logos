#!/usr/bin/env python3
"""has_svg / logo_svg 를 **파일 존재 기준**으로 맞춘다. 파일이 진실이다.

두 플래그가 파일과 어긋나는 사고가 반복됐다:
  · 2026-09-03  logo_svg=true(bool)·has_svg 누락 6,294건 — 'SVG 있음' 필터가 이들을 뺐다
  · 2026-09-04  1차 승격 20건(pooq-co·airbnb-co…)이 has_svg=false 로 되돌아감 —
                중간에 낀 다른 프로세스가 옛 스냅샷으로 플래그를 덮었다.
                파일은 있는데 사이트는 PNG 를 서비스했다(SVG 40,462→40,435).
비트맵을 감싼 SVG(<image / data:image)는 SVG 로 치지 않는다 (CLAUDE.md 원칙).
일일 크론에서 slim 만들기 직전에 돌린다.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import atomic_json

C = Path(__file__).resolve().parent.parent / "_clients"


def real_svg(p: Path) -> bool:
    try:
        h = p.read_bytes()[:8000].decode("utf-8", "ignore")
    except Exception:
        return False
    return "<svg" in h and "<image" not in h and "data:image/" not in h


def main():
    dry = "--dry-run" in sys.argv
    with atomic_json.locked(C / "brands.json"):
        raw = json.loads((C / "brands.json").read_text())
        br = raw["brands"] if isinstance(raw, dict) else raw
        on = off = fixed = 0
        for b in br:
            p = C / b["id"] / "logo.svg"
            has = p.exists() and real_svg(p)
            if has and not (b.get("has_svg") and b.get("logo_svg") == "logo.svg"):
                b["has_svg"] = True; b["logo_svg"] = "logo.svg"; on += 1
            elif not has and (b.get("has_svg") or b.get("logo_svg")):
                b["has_svg"] = False; b["logo_svg"] = None; off += 1
            elif b.get("logo_svg") is True:
                b["logo_svg"] = "logo.svg"; fixed += 1
        print(f"SVG 켬 {on} · 끔 {off} · bool 정규화 {fixed} · 총 SVG {sum(1 for b in br if b.get('has_svg')):,}")
        if dry or not (on or off or fixed):
            print("  (--dry-run)" if dry else "  변경 없음"); return
        if isinstance(raw, dict): raw["brands"] = br
        atomic_json.write_json(C / "brands.json", raw if isinstance(raw, dict) else br)
        print("  ✅ 저장")


if __name__ == "__main__":
    main()
