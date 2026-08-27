#!/usr/bin/env python3
"""수집 대기 목록(collect-wanted / svg-wanted)을 합집합으로 합친다.

왜 필요한가 —
이 파일들은 **사람이 손으로 넣은 항목이 쌓이는 목록**이다. rebase 충돌에서
한쪽을 통째로 고르면(--ours/--theirs) 반대편의 수동 등록이 조용히 사라진다.
2026-08-27 에 collect-wanted.json 이 충돌했고, 그대로 뒀으면 그날 넣은
31건이 없어졌을 것이다.

브랜드 배열을 키(id 또는 name_ko+name_en)로 합집합한다. 순수 추가라 안전하다.

  python3 scripts/merge-wanted-json.py OURS THEIRS OUT
"""
import json, sys


def key(b):
    return b.get("id") or f"{b.get('name_ko','')}|{b.get('name_en','')}"


def items(d):
    if isinstance(d, list):
        return d
    for k in ("brands", "items"):
        if isinstance(d.get(k), list):
            return d[k]
    return []


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    ours = json.load(open(sys.argv[1]))
    theirs = json.load(open(sys.argv[2]))
    a, b = items(ours), items(theirs)
    seen = {key(x) for x in a}
    added = 0
    for x in b:
        if key(x) not in seen:
            a.append(x)
            seen.add(key(x))
            added += 1
    if isinstance(ours, dict):
        for k in ("brands", "items"):
            if isinstance(ours.get(k), list):
                ours[k] = a
        if "count" in ours:
            ours["count"] = len(a)
    else:
        ours = a
    json.dump(ours, open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
    print(f"대기목록 병합 — {len(a)}건 (반대편에서 추가 {added})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
