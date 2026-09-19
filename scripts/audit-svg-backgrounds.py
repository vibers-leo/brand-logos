#!/usr/bin/env python3
"""SVG 흰 배경을 안전하게 찾는다.

모든 흰색을 지우지 않는다. 로고의 흰 글자·하이라이트는 보존해야 하므로,
viewBox 전체를 덮는 첫 번째 rect/path만 후보로 보고 원본은 그대로 둔다.
--apply를 주면 후보에 한해 별도 `logo-transparent.svg`를 만들며 원본은 보존한다.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]/'_clients'
WHITE={'#fff','#ffffff','white','rgb(255,255,255)','rgb(100%,100%,100%)'}

def norm(v): return re.sub(r'\s+','',v or '').lower()
def is_white(v): return norm(v) in WHITE

def candidate(p):
    try: root=ET.parse(p).getroot()
    except Exception: return None
    vb=root.get('viewBox','').replace(',',' ').split()
    width=root.get('width',''); height=root.get('height','')
    # conservative: only a root-level rect with explicit full-canvas dimensions.
    for i,ch in enumerate(list(root)):
        tag=ch.tag.rsplit('}',1)[-1]
        if tag!='rect': continue
        fill=ch.get('fill')
        if not is_white(fill):
            st=ch.get('style','')
            m=re.search(r'(?i)(?:^|;)fill\s*:\s*([^;]+)',st)
            if not m or not is_white(m.group(1)): continue
        x=norm(ch.get('x','0')); y=norm(ch.get('y','0'))
        w=norm(ch.get('width','')); h=norm(ch.get('height',''))
        full=(x in ('','0') and y in ('','0') and w in ('100%','100vw') and h in ('100%','100vh'))
        if vb and len(vb)>=4 and w==norm(vb[2]) and h==norm(vb[3]): full=True
        if full: return {'element_index':i,'fill':fill or 'style','viewBox':root.get('viewBox')}
    return None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--apply',action='store_true'); ap.add_argument('--limit',type=int,default=0); ap.add_argument('--max-files',type=int,default=5000, help='검사할 SVG 최대 수'); ap.add_argument('--output',default='_reports/svg-background-audit.json'); args=ap.parse_args()
    rows=[]
    checked=0
    for p in ROOT.glob('*/logo.svg'):
        checked += 1
        if args.max_files and checked > args.max_files: break
        hit=candidate(p)
        if hit:
            row={'file':str(p.relative_to(ROOT)),'candidate':hit}
            if args.apply:
                out=p.with_name('logo-transparent.svg')
                if not out.exists():
                    text=p.read_text(errors='ignore')
                    # Remove only the exact element selected by index, preserving every other white fill.
                    try:
                        root=ET.fromstring(text); children=list(root); root.remove(children[hit['element_index']]); out.write_text(ET.tostring(root,encoding='unicode'))
                        row['variant']=str(out.relative_to(ROOT))
                    except Exception as e: row['error']=str(e)
            rows.append(row)
            if args.limit and len(rows)>=args.limit: break
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({'count':len(rows),'items':rows},ensure_ascii=False,indent=2)+'\n')
    print(f'background candidates: {len(rows)} -> {out}')
if __name__=='__main__': main()
