#!/usr/bin/env python3
"""`_deleted.json` 에 올라간 브랜드의 폴더·레코드를 걷어낸다.

지웠는데 **되살아나는** 일이 있다. 생성기가 여럿이고(build-brand-json ·
build-logo-variants · build-variants) 각자 자기 시점의 brands.json 을 보기
때문에, 크론이 지우기 직전 스냅샷으로 돌면 폴더를 다시 만든다.
2026-09-03 에 ufc-graphic-sheet 의 brand.json·variants.json 이 그렇게
돌아와 GitHub Pages 폴백으로 계속 서빙됐다 — 버킷에서는 지웠는데도.

생성기를 하나씩 고치는 대신 **파이프라인 끝에서 한 번 걷어낸다.**
어느 생성기가 되살리든 여기서 잡힌다.
"""
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import atomic_json

C = Path(__file__).resolve().parent.parent / "_clients"


def main():
    dry = "--dry-run" in sys.argv
    ids = set(json.loads((C / "_deleted.json").read_text()))
    folders = [i for i in ids if (C / i).is_dir()]

    with atomic_json.locked(C / "brands.json"):
        raw = json.loads((C / "brands.json").read_text())
        br = raw["brands"] if isinstance(raw, dict) else raw
        back = [b["id"] for b in br if b["id"] in ids]

        print(f"삭제 대장 {len(ids)}건 · 폴더 잔존 {len(folders)} · 레코드 부활 {len(back)}")
        for i in folders[:10]:
            print(f"   폴더  {i}")
        for i in back[:10]:
            print(f"   레코드 {i}")
        if dry:
            print("  (--dry-run)")
            return
        if back:
            br = [b for b in br if b["id"] not in ids]
            if isinstance(raw, dict):
                raw["brands"] = br; raw["total"] = len(br)
            atomic_json.write_json(C / "brands.json", raw if isinstance(raw, dict) else br)

    for i in folders:
        shutil.rmtree(C / i, ignore_errors=True)
    if folders or back:
        print(f"  ✅ 폴더 {len(folders)} · 레코드 {len(back)} 정리")
    else:
        print("  변경 없음")


if __name__ == "__main__":
    main()
