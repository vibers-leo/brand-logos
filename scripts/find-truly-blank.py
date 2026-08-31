#!/usr/bin/env python3
"""진짜로 빈 로고만 찾는다 — 색이 아니라 **불투명 픽셀**로 판정한다.

잉크 비율(흰 배경 대비 어두운 픽셀)로 재면 노란색·흰색 로고가 전부
'빈 이미지'로 잡힌다. 실제로 177건을 시트로 뽑아 보니 스냅챗·소니·
유니티·아스날이 다 들어 있었다 — 밝은 색이라 그런 것뿐이다.

알파 채널을 보면 색과 무관하게 내용 유무를 알 수 있다.

  python3 scripts/find-truly-blank.py
  python3 scripts/find-truly-blank.py --apply
"""
import io, json, os, signal, sys
import numpy as np
from PIL import Image

class T(Exception): pass
signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(T()))

def opaque_ratio(path):
    if path.endswith(".svg"):
        import cairosvg
        png = cairosvg.svg2png(url=path, output_width=200)
        im = Image.open(io.BytesIO(png)).convert("RGBA")
    else:
        im = Image.open(path).convert("RGBA")
        im.thumbnail((200, 200))
    a = np.array(im)
    alpha = a[..., 3]
    opaque = alpha > 24
    if not opaque.any(): return 0.0, 0.0
    # ⚠️ '흰색이 아닌 픽셀'로만 재면 **흰색 로고**가 빈 것으로 잡힌다.
    #    소니·유니티·아스날이 실제로 그렇게 걸렸다(다크 배경용 흰 로고).
    #    흰 사각형 플레이스홀더와의 차이는 색이 아니라 **모양**이다:
    #      흰 로고        → 불투명 픽셀이 글자·심볼 모양이라 비율이 낮다
    #      흰 사각형      → 화면 전체가 불투명하다
    rgb = a[..., :3].astype(int)
    o = float(opaque.mean())
    if o > 0.92 and bool((rgb[opaque] > 246).all()):
        return o, 0.0      # 전면이 순백 = 플레이스홀더
    return round(o, 4), round(o, 4)

def main():
    d = json.load(open("_clients/_bad-logos.json"))["bad"]
    cand = [x for x in d if x[2] == "거의빈이미지"]
    真 = []
    for bid, name, _, _ in cand:
        base = f"_clients/{bid}"
        p = base + "/logo.svg" if os.path.exists(base + "/logo.svg") else base + "/logo.png"
        if not os.path.exists(p):
            真.append([bid, name, "파일없음", 0]); continue
        try:
            signal.alarm(8); o, c = opaque_ratio(p); signal.alarm(0)
        except Exception:
            signal.alarm(0); continue
        if c < 0.002:
            真.append([bid, name, "내용없음", c])
    print(f"  후보 {len(cand)} → 진짜 빈 것 {len(真)}")
    for x in 真: print(f"   {x[0][:28]:<30} {str(x[1])[:20]:<22} {x[3]}")
    if "--apply" in sys.argv and 真:
        doc = json.load(open("_clients/brands.json"))
        ids = {x[0]: x[2] for x in 真}
        n = 0
        for b in doc["brands"]:
            if b["id"] in ids:
                b["hidden"] = True; b["hidden_reason"] = f"빈 이미지({ids[b['id']]})"; n += 1
        json.dump(doc, open("_clients/brands.json", "w"),
                  ensure_ascii=False, separators=(",", ":"))
        print(f"  ✅ hidden {n}건")

main()
