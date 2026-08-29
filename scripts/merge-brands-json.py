#!/usr/bin/env python3
"""brands.json 두 판본을 의미 단위로 합친다.

왜 필요한가 —
brands.json 은 40,291개가 들어간 **한 줄짜리 압축 JSON** 이라 git 이 텍스트로
병합하지 못한다. 그런데 자동수집 워크플로는 5시간 돌기 때문에, 그 사이
사람이 푸시하면 러너의 푸시가 'fetch first' 로 거부되고 그 단계가 죽는다.
2026-08-26 에 실제로 그렇게 5시간치 후반 산출물이 버려졌다.

병합 규칙 (양쪽 다 살린다):
  · 기준은 ours(러너가 방금 계산한 것) — 파생 필드가 최신이다
  · theirs(원격)에만 있는 브랜드는 추가한다
  · 같은 브랜드면 sources 를 file 기준으로 합집합한다
    (사람이 손으로 넣은 워드마크 소스가 러너 판본엔 없다)
  · theirs 에만 있는 키는 **aliases 만** 가져온다

⚠️ 임의 필드를 되살리면 안 된다. 한쪽이 **일부러 내린 플래그**를 부활시킨다.
   실제로 2026-08-26 러너가 has_png 를 105개 강등했는데(그건 그것대로 버그였다),
   무차별 보강이면 그 판단을 조용히 뒤집었을 것이다. 어느 쪽이 맞는지는
   파일 존재 여부로만 알 수 있고, 병합 시점엔 그 정보가 없다.
   sources 합집합과 신규 브랜드 추가는 순수 추가라 안전하다.

⚠️ 다만 **삭제 앞에서는 안전하지 않다.** 합집합은 '지웠다'를 모른다.
   2026-08-29 에 로고가 아닌 항목 43건(사진·UI아이콘·타 브랜드 로고)을
   지우고 rebase 했더니 원격 옛 데이터에서 **전부 되살아났다.**
   그래서 `_clients/_deleted.json` 묘비를 둔다 — 여기 적힌 id 는 어느 쪽에
   있든 결과에서 뺀다. 브랜드를 지울 때 이 파일에도 함께 적는다.

  python3 scripts/merge-brands-json.py OURS THEIRS OUT
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOMB = ROOT / "_clients" / "_deleted.json"


def load(p):
    d = json.load(open(p))
    return d, (d["brands"] if isinstance(d, dict) else d)


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    ours_doc, ours = load(sys.argv[1])
    _, theirs = load(sys.argv[2])
    om = {b["id"]: b for b in ours}

    added = merged_src = merged_key = 0
    for tb in theirs:
        ob = om.get(tb["id"])
        if ob is None:
            ours.append(tb)
            om[tb["id"]] = tb
            added += 1
            continue
        have = {s.get("file") for s in (ob.get("sources") or [])}
        for s in (tb.get("sources") or []):
            if s.get("file") not in have:
                ob.setdefault("sources", []).append(s)
                merged_src += 1
        # 사람이 손으로 넣고 생성기가 지우지 않는 필드만 보강한다
        for k in ("aliases",):
            v = tb.get(k)
            if v and not ob.get(k):
                ob[k] = v
                merged_key += 1

    # 묘비 — 의도적으로 지운 id 는 어느 쪽에 있든 뺀다
    revived = 0
    if TOMB.exists():
        try:
            dead = set(json.loads(TOMB.read_text()))
        except Exception as e:
            print(f"❌ 묘비 파일을 읽을 수 없다 ({type(e).__name__}) — 병합을 중단한다")
            return 1
        keep = [b for b in ours if b.get("id") not in dead]
        revived = len(ours) - len(keep)
        if revived:
            ours[:] = keep
            if isinstance(ours_doc, dict):
                ours_doc["brands"] = ours

    out = sys.argv[3]
    json.dump(ours_doc, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"병합 완료 — 브랜드 {len(ours):,}개 "
          f"(원격에서 추가 {added} · sources 합침 {merged_src} · aliases 보강 {merged_key}"
          + (f" · 묘비로 제거 {revived}" if revived else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
