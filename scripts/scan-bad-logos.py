#!/usr/bin/env python3
"""로고답지 않은 이미지를 찾는다 — 사진·문장·빈 이미지·통짜 배너.

⚠️ 거대 SVG 는 렌더에서 CPU 루프에 빠진다. 실제로 43,473개 중
   10,000번째 근처에서 38분 넘게 한 파일에 갇혔다. 그래서
   **크기 상한을 두고 건너뛴다** — 건너뛴 것은 결과에 따로 남긴다.

부분 결과를 계속 저장해 중단해도 이어서 돌릴 수 있다.

  python3 scripts/scan-bad-logos.py
  python3 scripts/scan-bad-logos.py --apply   # hidden 플래그까지 적용
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import collect_krx_lib as L

OUT = "_clients/_bad-logos.json"
MAX_SVG = 1_500_000   # 이보다 큰 SVG 는 렌더가 위험하다
MAX_PNG = 12_000_000

def main():
    d = json.load(open("_clients/brands.json"))["brands"]
    done, bad = {}, []
    if os.path.exists(OUT):
        prev = json.load(open(OUT))
        bad = prev.get("bad", []); done = {x[0]: 1 for x in bad}
        done.update({k: 1 for k in prev.get("ok", [])})
    ok = list(json.load(open(OUT)).get("ok", [])) if os.path.exists(OUT) else []
    skipped = []
    n = 0
    for b in d:
        bid = b["id"]
        if bid in done: continue
        base = f"_clients/{bid}"
        p = base + "/logo.svg" if os.path.exists(base + "/logo.svg") else base + "/logo.png"
        if not os.path.exists(p): continue
        sz = os.path.getsize(p)
        lim = MAX_SVG if p.endswith(".svg") else MAX_PNG
        if sz > lim:
            skipped.append([bid, sz]); ok.append(bid); n += 1; continue
        name = b.get("name_ko") or b.get("name_en")
        try:
            r, _, _ = L.ink_ratio(open(p, "rb").read(), p.endswith(".svg"))
        except Exception:
            bad.append([bid, name, "렌더실패", 0]); n += 1; continue
        if   r == -2.0: bad.append([bid, name, "문장이미지", 0])
        elif r == -3.0: bad.append([bid, name, "사진", 0])
        elif 0 <= r < 0.004: bad.append([bid, name, "거의빈이미지", round(r, 4)])
        elif r > 0.88:  bad.append([bid, name, "통짜배너", round(r, 3)])
        else: ok.append(bid)
        n += 1
        if n % 500 == 0:
            json.dump({"bad": bad, "ok": ok, "skipped": skipped},
                      open(OUT, "w"), ensure_ascii=False)
            print(f"  {n} 검사 · 의심 {len(bad)}", flush=True)
    json.dump({"bad": bad, "ok": ok, "skipped": skipped},
              open(OUT, "w"), ensure_ascii=False)
    from collections import Counter
    print(f"✅ 검사 {n} · 의심 {len(bad)} · 크기초과 건너뜀 {len(skipped)}")
    print("  ", Counter(x[2] for x in bad).most_common())

main()
