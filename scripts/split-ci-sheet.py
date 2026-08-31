#!/usr/bin/env python3
"""CI 매뉴얼 페이지 한 장에서 여러 로고 변형을 각각 떼어낸다.

군포시 logo.png 가 그랬다 — 1200x1667 한 장에 기본형·태그라인·조합형
세 버전과 최소사용크기 규정 예시, 설명문, 헤더바가 전부 들어 있었다.

핵심은 **유채색만 본다**는 것이다. 헤더바(회색)·설명문(검정)·치수선은
무채색이고 로고는 브랜드 컬러다. 잉크량만 보면 군포는 헤더바가
75,964 로 로고(20,811)보다 많아 헤더를 로고로 착각한다.

무채색 로고(검정 워드마크 등)에는 쓸 수 없다 — 그래서 자동 적용하지
않고 후보를 뽑아 사람이 확인한 뒤 돌린다.
"""
import sys, os, io, json
from PIL import Image
import numpy as np

VGAP = 100   # 세로로 이만큼 떨어지면 다른 변형
HGAP = 50    # 가로로 이만큼 떨어지면 다른 열(오른쪽 = 규정 예시)
MIN_INK = 1500

def analyze(path):
    im = Image.open(path).convert("RGBA")
    a = np.array(im); H, W = a.shape[:2]
    rgb = a[..., :3].astype(int)
    chroma = rgb.max(2) - rgb.min(2)
    ink = (a[..., 3] > 40) & (rgb.max(2) < 235) & (chroma > 40)
    if ink.sum() < MIN_INK:
        return im, None
    row = ink.sum(1)
    # 세로 덩어리 → VGAP 으로 그룹 병합
    runs, s = [], None
    for y in range(H + 1):
        v = row[y] if y < H else 0
        if v > 0 and s is None: s = y
        elif v == 0 and s is not None:
            if y - s > 12: runs.append([s, y])
            s = None
    if not runs: return im, None
    groups = [runs[0]]
    for r in runs[1:]:
        if r[0] - groups[-1][1] < VGAP: groups[-1][1] = r[1]
        else: groups.append(r)
    out = []
    for t, b in groups:
        band = ink[t:b]
        if band.sum() < MIN_INK: continue
        col = band.sum(0)
        # 가로 덩어리 → HGAP 으로 열 분리, 잉크 최다 열만 (= 큰 버전)
        cr, s = [], None
        for x in range(W + 1):
            v = col[x] if x < W else 0
            if v > 0 and s is None: s = x
            elif v == 0 and s is not None:
                cr.append([s, x]); s = None
        cols = [cr[0]]
        for c in cr[1:]:
            if c[0] - cols[-1][1] < HGAP: cols[-1][1] = c[1]
            else: cols.append(c)
        l, r = max(cols, key=lambda c: int(col[c[0]:c[1]].sum()))
        if int(col[l:r].sum()) < MIN_INK: continue
        # 선택한 열 기준으로 세로 재조정 (다른 열 때문에 늘어난 여백 제거)
        sub = ink[t:b, l:r]; ri = np.where(sub.sum(1) > 0)[0]
        t2, b2 = t + ri.min(), t + ri.max() + 1
        out.append((l, t2, r, b2, int(sub.sum())))
    return im, out

def main():
    args = [x for x in sys.argv[1:] if not x.startswith("-")]
    write = "--write" in sys.argv
    for bid in args:
        p = f"_clients/{bid}/logo.png"
        if not os.path.exists(p): print(f"  ⚠️ {bid} 없음"); continue
        im, boxes = analyze(p)
        if not boxes or len(boxes) < 2:
            print(f"  — {bid}: 변형 {len(boxes or [])}개 (분리 안 함)"); continue
        print(f"  ✂️ {bid}: 변형 {len(boxes)}개")
        for i, (l, t, r, b, k) in enumerate(boxes, 1):
            pad = 12
            box = (max(0, l - pad), max(0, t - pad),
                   min(im.width, r + pad), min(im.height, b + pad))
            crop = im.crop(box)
            print(f"     {i}. {crop.width}x{crop.height} 잉크{k}")
            if write:
                os.makedirs(f"_clients/{bid}/variants", exist_ok=True)
                crop.save(f"_clients/{bid}/variants/ci-{i}.png")
            else:
                crop.convert("RGB").save(f"/tmp/{bid}-{i}.png")

main()
