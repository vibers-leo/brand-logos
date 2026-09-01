#!/usr/bin/env python3
"""큰 SVG 를 svgo 로 줄이되, **렌더가 같을 때만** 반영한다.

2MB 넘는 logo.svg 가 44개 있었다. 사용자가 실제로 내려받는 파일이고,
품질 스캔이 CPU 루프에 갇힌 것도 이런 파일들 때문이다.
Inkscape 메타데이터·중복 좌표가 대부분이라 31~63% 가 줄었다.

⚠️ svgo 는 가끔 렌더를 깨뜨린다. 그래서 최적화 전후를 300px 로 렌더해
   픽셀 평균차가 1.5 미만일 때만 교체한다. 아니면 원본을 그대로 둔다.

  python3 scripts/optimize-large-svg.py --min-mb 2 --dry-run
  python3 scripts/optimize-large-svg.py --min-mb 2 --apply
"""
import io, os, shutil, subprocess, sys, tempfile
import numpy as np
from PIL import Image
import cairosvg

def render(path, w=300):
    return Image.open(io.BytesIO(cairosvg.svg2png(url=path, output_width=w))).convert("RGBA")

def main():
    mb = 2.0
    if "--min-mb" in sys.argv: mb = float(sys.argv[sys.argv.index("--min-mb")+1])
    apply_ = "--apply" in sys.argv
    lim = int(mb * 1024 * 1024)
    targets = []
    for root, _, files in os.walk("_clients"):
        if "/sources/" in root: continue        # 격리 보관물은 서비스 대상이 아니다
        for f in files:
            if f != "logo.svg": continue
            p = os.path.join(root, f)
            if os.path.getsize(p) > lim: targets.append(p)
    print(f"  대상 {len(targets)}개 ({mb}MB 초과)")
    saved = ok = skip = fail = 0
    for p in sorted(targets, key=os.path.getsize, reverse=True):
        a = os.path.getsize(p)
        tmp = tempfile.mktemp(suffix=".svg")
        # ⚠️ svgo 는 path 가 복잡하면 몇 분씩 걸린다. 시간으로 끊고 넘어간다.
        try:
            r = subprocess.run(["svgo", "--multipass", "-i", p, "-o", tmp],
                               capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            print(f"   ⏱️ {p.split('/')[1][:30]:<32} svgo 시간 초과 — 원본 유지")
            fail += 1; continue
        if r.returncode != 0 or not os.path.exists(tmp):
            fail += 1; continue
        b = os.path.getsize(tmp)
        try:
            ia, ib = render(p), render(tmp)
            if ia.size != ib.size: raise ValueError("크기 다름")
            d = float(np.abs(np.array(ia).astype(int) - np.array(ib).astype(int)).mean())
        except Exception as e:
            print(f"   ⚠️ {p[9:40]:<32} 검증 실패 {type(e).__name__}")
            os.unlink(tmp); skip += 1; continue
        name = p.split("/")[1]
        if d >= 1.5:
            print(f"   ⚠️ {name[:30]:<32} 렌더 다름 {d:.2f} — 원본 유지")
            os.unlink(tmp); skip += 1; continue
        print(f"   {name[:30]:<32} {a/1024/1024:5.1f} → {b/1024/1024:5.1f} MB")
        # ⚠️ os.replace 는 볼륨을 넘지 못한다(Cross-device link).
        #    _clients 는 외장 SSD, tempfile 은 시스템 /tmp 라 서로 다른 볼륨이다.
        if apply_: shutil.copyfile(tmp, p); os.unlink(tmp)
        else: os.unlink(tmp)
        saved += a - b; ok += 1
    print(f"\n  최적화 {ok} · 원본유지 {skip} · 실패 {fail} · 절감 {saved/1024/1024:.1f}MB")
    if not apply_: print("  (--apply 없으면 반영 안 함)")

main()
