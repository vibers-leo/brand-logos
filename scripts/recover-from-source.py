#!/usr/bin/env python3
"""폴더는 있는데 brands.json 에 레코드가 없는 브랜드를 `_source.json` 으로 되살린다.

두 가지 사고를 각각 겪었고 둘 다 이 스크립트로 복구했다:
  ① 동시 쓰기로 파일 파손      → 직전 커밋 복원 후 357건 재구성
  ② 동시 read-modify-write     → 마지막 writer 가 덮어써 148건 소실

②는 파일이 멀쩡해서 **에러가 안 난다.** 폴더 수와 레코드 수를 대조하기
전에는 아무도 모른다. 그래서 이 스크립트는 수집 사이클마다 돌린다.

`_source.json` 이 없는 폴더는 손대지 않는다 — 일부러 지운 중복·변형일 수 있다.
"""
import json, os, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import atomic_json

C = Path(__file__).resolve().parent.parent / "_clients"
KIND = {"franchise-rendered": "프랜차이즈", "gov-rendered": "공공기관"}
CAT  = {"franchise-rendered": "식음료", "gov-rendered": "공공기관", "krx-rendered": "기타"}


def build(meta: dict, folder: Path) -> dict:
    bid  = meta["id"]
    site = meta.get("site") or ""
    svg  = (folder / "logo.svg").exists()
    png  = (folder / "logo.png").exists()
    src  = meta.get("source", "")
    r = {
        "id": bid, "name_ko": meta.get("name"), "name_en": meta.get("name"),
        "category": CAT.get(src, "기타"),
        "folder": f"_clients/{bid}", "website": site,
        "domain": re.sub(r"^https?://(www\.)?|/.*$", "", site).lower(),
        "logo_svg": "logo.svg" if svg else None, "has_svg": svg,
        "logo_png": png, "has_png": png,
        "svg_source": src, "origin": "KR",
        "added_at": (meta.get("collected_at") or time.strftime("%Y-%m-%d"))[:10],
        "recovered": True,
    }
    if KIND.get(src):
        r["kr_kind"] = KIND[src]
    for k_meta, k_rec in (("code", "krx_code"), ("market", "krx_market"), ("sector", "krx_sector")):
        if meta.get(k_meta):
            r[k_rec] = meta[k_meta]
    return r


def main():
    dry = "--dry-run" in sys.argv
    with atomic_json.locked(C / "brands.json"):
        raw = json.loads((C / "brands.json").read_text())
        cur = raw["brands"] if isinstance(raw, dict) else raw
        have = {b["id"] for b in cur}

        found, nometa = [], 0
        for d in sorted(os.listdir(C)):
            folder = C / d
            if not folder.is_dir() or d in have:
                continue
            meta = folder / "_source.json"
            if not meta.exists():
                nometa += 1
                continue
            try:
                m = json.loads(meta.read_text())
            except json.JSONDecodeError:
                print(f"  ⚠️ {d} — _source.json 파손, 건너뜀")
                continue
            if not (folder / "logo.svg").exists() and not (folder / "logo.png").exists():
                print(f"  ⚠️ {d} — 로고 파일 없음, 건너뜀")
                continue
            found.append(build(m, folder))

        print(f"복구 대상 {len(found)}건 · 메타 없어 건너뜀 {nometa}건")
        for r in found[:5]:
            print(f"    {r['id'][:24].ljust(26)} {(r['name_ko'] or '')[:18]}")
        if not found or dry:
            print("  (--dry-run — 저장 안 함)" if dry else "  변경 없음")
            return
        cur.extend(found)
        if isinstance(raw, dict):
            raw["brands"] = cur; raw["total"] = len(cur)
        atomic_json.write_json(C / "brands.json", raw if isinstance(raw, dict) else cur)
        print(f"  ✅ {len(found)}건 복구 (총 {len(cur):,})")


if __name__ == "__main__":
    main()
