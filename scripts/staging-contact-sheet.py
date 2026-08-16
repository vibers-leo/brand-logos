#!/usr/bin/env python3
"""스테이징에 받은 로고를 한 장의 대조 시트로 렌더한다.

왜 필요한가: 수집기가 통과시킨 파일이 **정말 그 브랜드의 로고인지**는
파일 검사로 알 수 없다. 위키데이터 연결 오류(롯데하이마트에 Lotte Mart 로고가
붙어 있었다)나 로고가 아닌 이미지(지도·인증마크)는 눈으로만 잡힌다.
과거에도 이 방식으로 kepco 의 '웹접근성 마크', fsec 의 '파트너 로고'를 잡았다.

사용:
  python3 scripts/staging-contact-sheet.py --dir _staging/korea-wikidata -o /tmp/sheet.html
"""
from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="_staging/korea-wikidata")
    ap.add_argument("-o", "--out", default="/tmp/staging-sheet.html")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--offset", type=int, default=0)
    args = ap.parse_args()

    base = ROOT / args.dir
    dirs = sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    dirs = dirs[args.offset:]
    if args.limit:
        dirs = dirs[:args.limit]

    cards = []
    for d in dirs:
        svg = d / "logo.svg"
        if not svg.exists():
            continue
        b64 = base64.b64encode(svg.read_bytes()).decode()
        size = svg.stat().st_size
        cards.append(
            f'<figure><div class="box"><img src="data:image/svg+xml;base64,{b64}" alt=""></div>'
            f'<figcaption>{html.escape(d.name)}<span>{size:,}B</span></figcaption></figure>')

    out = Path(args.out)
    out.write_text(f"""<!doctype html><meta charset="utf-8">
<title>스테이징 대조 시트 — {html.escape(args.dir)}</title>
<style>
 body{{font:14px/1.5 -apple-system,'Pretendard',sans-serif;margin:24px;background:#fafafa;color:#18181b}}
 h1{{font-size:18px}} .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px}}
 figure{{margin:0;background:#fff;border:1px solid #e4e4e7;border-radius:10px;overflow:hidden}}
 .box{{height:110px;display:flex;align-items:center;justify-content:center;padding:12px;
   background:repeating-conic-gradient(#f4f4f5 0 25%,#fff 0 50%) 0/16px 16px}}
 img{{max-width:100%;max-height:100%}}
 figcaption{{padding:7px 9px;font-size:11px;border-top:1px solid #f4f4f5;display:flex;
   justify-content:space-between;gap:6px;word-break:break-all}}
 figcaption span{{color:#a1a1aa;flex:none}}
</style>
<h1>스테이징 대조 시트 — {len(cards)}건 <small>({html.escape(args.dir)})</small></h1>
<p>브랜드명과 그림이 맞지 않는 것을 찾는다. 로고가 아닌 이미지(지도·인증마크·다른 회사)도 여기서 걸러진다.</p>
<div class="grid">{''.join(cards)}</div>
""")
    print(f"{len(cards)}건 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
