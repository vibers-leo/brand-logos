#!/usr/bin/env python3
"""붙여넣은 로고 요청 목록을 공식 사이트 수집 큐로 변환한다.

예:
  python3 scripts/create-logo-request-queue.py --text '동명대 / 영도문화원 / AMC(로고 제공)' \
    --output _targets/request-queue.json

URL이 확보된 항목만 collect-site-svg.mjs가 수집하고, 나머지는 needs_official_url 상태로 남겨
공식 주소 확인 뒤 같은 큐를 갱신할 수 있다. 사용자 제공 파일은 자동 수집하지 않고 별도 검수한다.
"""
from __future__ import annotations
import argparse, json, re
from datetime import date
from pathlib import Path

def parse(raw: str):
    # Slash/newline are the convention used in support requests. Commas are kept
    # because they can be part of a Korean brand name (예: 오늘, 만큼).
    parts = [p.strip() for p in re.split(r"\s*/\s*|\s*;\s*|\s*\n\s*", raw) if p.strip()]
    out=[]; seen=set()
    for part in parts:
        provided = bool(re.search(r"\(?\s*로고\s*제공\s*\)?", part))
        pending = bool(re.search(r"\(?\s*추후\s*전달\s*\)?", part))
        name = re.sub(r"\s*\(?\s*(?:로고\s*제공|추후\s*전달)\s*\)?", "", part).strip()
        if not name or name in seen: continue
        seen.add(name)
        out.append({"name":name,"slug":name,"source_state":
                    "user_provided" if provided else ("pending_delivery" if pending else "needs_official_url"),
                    "provided_file":None,"url":None})
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--text'); ap.add_argument('--input'); ap.add_argument('--output',required=True)
    args=ap.parse_args()
    raw=args.text if args.text is not None else Path(args.input).read_text()
    items=parse(raw); now=date.today().isoformat()
    doc={"created_at":now,"purpose":"사용자 요청 로고 수집 큐","usage":"node scripts/collect-site-svg.mjs --input <this-file>","items":items}
    p=Path(args.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n")
    print(f"created {p}: {len(items)} items")

if __name__=='__main__': main()
