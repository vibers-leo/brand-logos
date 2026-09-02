#!/usr/bin/env python3
"""브랜드 폴더에 `_source.json` 을 남긴다 — 홈페이지 주소가 핵심이다.

`brands.json` 은 여러 프로세스가 함께 쓰다가 통째로 덮어써질 수 있다.
2026-09-02 에 프랜차이즈 수집이 옛 스냅샷을 써서 **공공기관 25건이
목록에서 사라졌다.** 폴더와 이미지는 남았는데 '어느 브랜드인지'를 몰라
복구가 막혔다 — 홈페이지 주소가 없었기 때문이다.

폴더마다 출처를 적어 두면 목록이 깨져도 되살릴 수 있다.

  python3 scripts/write-source-meta.py --dry-run
  python3 scripts/write-source-meta.py
"""
import json, sys, time
from pathlib import Path

C = Path(__file__).resolve().parent.parent / "_clients"

def main():
    dry = "--dry-run" in sys.argv
    brands = json.loads((C / "brands.json").read_text())["brands"]
    wrote = skip = 0
    for b in brands:
        d = C / b["id"]
        if not d.is_dir():
            continue
        f = d / "_source.json"
        site = b.get("website") or b.get("domain") or ""
        if not site:
            skip += 1
            continue
        if f.exists():
            try:
                if json.loads(f.read_text()).get("site"):
                    skip += 1
                    continue
            except Exception:
                pass
        rec = {"id": b["id"], "name": b.get("name_ko") or b.get("name_en"),
               "site": site if site.startswith("http") else f"https://{site}",
               "source": b.get("svg_source") or "",
               "kr_kind": b.get("kr_kind") or "",
               "wikidata": b.get("wikidata") or "",
               "written_at": time.strftime("%Y-%m-%d %H:%M")}
        rec = {k: v for k, v in rec.items() if v}
        if not dry:
            f.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
        wrote += 1
    print(f"  기록 {wrote:,} · 건너뜀(주소 없음·이미 있음) {skip:,}")
    if dry:
        print("  (--dry-run — 파일 안 씀)")

main()
