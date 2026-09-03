#!/usr/bin/env python3
"""사이트 모달에서 손으로 찍은 '검정/흰 배경' 지정을 Firestore 에서 내려받는다.

  logo_votes/{id}.bg = "dark" | "light"   (bg_by = 찍은 사람 이메일)
  → _clients/bg-overrides.json  {id: "dark"|"light"}

detect-white-logos.py 가 이 파일을 읽어 자동 판정보다 우선 적용한다.
자동은 '흰 잉크 60% 이상'까지만 검정으로 보낸다. 45~60% 는 흰 글자형과
흰 채움 아이콘형이 반반이라 기계가 못 가른다 — 그 구간이 손가락의 몫이다.

logo_votes 는 규칙이 read: if true 라 Admin 키 없이 **공개 REST** 로 읽는다.
API 키는 semologo/.env.local 의 NEXT_PUBLIC_FIREBASE_API_KEY (브라우저에 이미 노출된 키).
관리자 이메일이 아닌 사람이 쓴 bg 는 무시한다 — 규칙이 write: if true 라 누구나 쓸 수 있다.
"""
import json, os, sys, urllib.request, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import atomic_json

C = Path(__file__).resolve().parent.parent / "_clients"
PROJECT = "ai-recipe-lab"
ADMIN = "juuuno1116@gmail.com"
ENV = Path("/Volumes/Untitled/dev/nextjs-apps/semologo/.env.local")


def api_key():
    k = os.environ.get("NEXT_PUBLIC_FIREBASE_API_KEY")
    if k: return k
    for line in ENV.read_text().splitlines():
        if line.startswith("NEXT_PUBLIC_FIREBASE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    sys.exit("NEXT_PUBLIC_FIREBASE_API_KEY 없음 — semologo/.env.local 확인")


def main():
    key = api_key()
    base = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents/logo_votes"
    out, tok, n = {}, None, 0
    while True:
        q = {"pageSize": 300, "key": key, "mask.fieldPaths": ["bg", "bg_by"]}
        if tok: q["pageToken"] = tok
        url = base + "?" + urllib.parse.urlencode(q, doseq=True)
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.load(r)
        for doc in d.get("documents", []):
            n += 1
            f = doc.get("fields", {})
            bg = f.get("bg", {}).get("stringValue")
            by = f.get("bg_by", {}).get("stringValue")
            if bg in ("dark", "light") and by == ADMIN:
                out[doc["name"].rsplit("/", 1)[-1]] = bg
        tok = d.get("nextPageToken")
        if not tok: break
    p = C / "bg-overrides.json"
    atomic_json.write_json(p, dict(sorted(out.items())), indent=1)
    print(f"✅ 문서 {n:,}개 중 수동 지정 {len(out)}건 → {p.name}  "
          f"(dark {sum(1 for v in out.values() if v=='dark')} · light {sum(1 for v in out.values() if v=='light')})")


if __name__ == "__main__":
    main()
