#!/usr/bin/env python3
"""
'밝은 로고'를 찾아 brands.json 에 light_logo 를 붙인다.

왜 필요한가
-----------
흰색·아주 밝은 로고는 목록 카드의 밝은 배경에서 보이지 않아 **빈 카드처럼**
보인다. 사이트는 light 플래그가 붙은 카드만 어두운 배경으로 그린다.

판정은 채도가 아니라 **밝기**로 한다. 채도로 보면 컬러 아이콘 + 흰 글자
조합이 'color' 로 나와서 놓친다. logo.svg 를 투명 배경으로 렌더해
잉크 픽셀의 40% 이상이 luma>235 면 밝은 로고로 본다.

logo-transparent.png 로는 판정할 수 없다 — 그 파일은 흰색을 이미
제거해버려서 흰 글자가 안 보인다.

사용:
  python3 scripts/scan-light-logos.py          # 스캔 + brands.json 갱신
"""
import sys
import json
import collections
from pathlib import Path

import numpy as np

# logoform 은 같은 scripts/ 안에 있다. 레포 루트에서 실행하든 scripts/ 안에서
# 실행하든 찾도록 이 파일의 위치를 기준으로 넣는다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import logoform as L
C=Path('_clients')
brands=json.load(open(C/'brands.json'))['brands']
frac={}
for i,b in enumerate(brands):
    p=C/b['id']/'logo.svg'
    if not p.exists(): continue
    arr=L.render(p, 300)          # 판정만 하면 되니 작게 렌더
    if arr is None: continue
    m=L.ink_mask(arr)
    if m.sum()<50: continue
    px=arr[...,:3][m].astype(np.int16)
    lum=0.299*px[:,0]+0.587*px[:,1]+0.114*px[:,2]
    frac[b['id']]=round(float((lum>235).mean()),3)
    if (i+1)%1000==0: print(f'  {i+1}개 처리', flush=True)
json.dump(frac, open('/tmp/svg_lum.json','w'))

THRESHOLD = 0.4
light = {k for k, v in frac.items() if v > THRESHOLD}
data = json.load(open(C/'brands.json'), object_pairs_hook=collections.OrderedDict)
changed = 0
for b in data['brands']:
    was, now = bool(b.get('light_logo')), b['id'] in light
    if now and not was:
        b['light_logo'] = True; changed += 1
    elif was and not now:
        b.pop('light_logo', None); changed += 1
if changed:
    json.dump(data, open(C/'brands.json', 'w'), ensure_ascii=False, indent=2)
print(f'light_logo 갱신 {changed}건 (총 {len(light)}개)')
n=sum(1 for v in frac.values() if v>0.4)
print(f'완료 {len(frac):,}개 | 흰색 40% 초과 {n}개')
