#!/usr/bin/env python3
"""theSVG 레지스트리에서 **미보유 브랜드**를 새로 등록한다.

왜 이 소스인가 —
발굴 파일(thesvg-discovery.json)의 form_gaps 는 허수였다. theSVG 의
forms:["symbol"] 은 자기네 분류라 우리 정의와 달라서, 받아보면 같은 로고를
색만 바꾼 것이었다(3M 검정→빨강, 4D 검정→파랑). 종횡비 필터에 6건 중 5건이
걸렸다. 반면 **new_brands 는 우리에게 아예 없는 브랜드**라 성격이 다르다.
표본 6건(Abarth·ADNOC·Affinity Designer 등)을 육안 확인했고 전부 진짜였다.

⚠️ 라이선스로 문을 건다. 발굴 파일의 policy 가 '상표 검토 전 반영 금지'인데,
   CC0/MIT/Apache/Unlicense 는 그 검토를 통과한 것으로 본다. brand-use·
   Trademark·CC-BY-ND·Fair Use·Unknown 은 건드리지 않는다.

⚠️ 중복 판정은 **정확 일치만** 쓴다. 부분일치는 오답 천지다 — 실측에서
   '한라IMS→ms', 'KICO→apache-flink-icon', '기현정공→hyundai-mobis' 가
   나왔다. 신규 등록에서 오답은 곧 중복 브랜드 생성이다.

⚠️ logo.png 를 함께 만든다. build-variants.py 가 logo.png 를 이미 있다고
   전제하므로, 안 만들면 PNG 다운로드가 전부 404 다.

  python3 scripts/collect-new-thesvg.py --dry-run
  python3 scripts/collect-new-thesvg.py --limit 30
  python3 scripts/collect-new-thesvg.py
"""
import io, json, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
REG = "https://thesvg.org/api/registry.json"
SVG = "https://thesvg.org/icons/{slug}/{variant}.svg"
UA = "VibersLogoCollector/1.0 (https://semologo.com)"
FREE = {"CC0-1.0", "MIT", "Apache-2.0", "Unlicense"}

# theSVG 카테고리 → 우리 카테고리
CAT = {
    "AI": "IT·테크", "Software": "IT·테크", "Platform": "IT·테크",
    "Devtool": "IT·테크", "DevTool": "IT·테크", "Library": "IT·테크",
    "Database": "IT·테크", "Networking": "IT·테크", "Security": "IT·테크",
    "Cloud": "IT·테크", "Hosting": "IT·테크", "Hardware": "IT·테크",
    "Finance": "금융·결제", "Fintech": "금융·결제", "Crypto": "금융·결제",
    "Community": "미디어·엔터", "Social": "미디어·엔터", "Media": "미디어·엔터",
    "Gaming": "게임", "Game": "게임",
    "Education": "교육", "Health": "의료·바이오", "Automotive": "자동차",
    "Energy": "에너지·화학", "Retail": "유통·쇼핑", "Logistics": "물류·교통",
    "Government": "공공·기관",
}


def get(url, timeout=40):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout).read()


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def ink_ratio(svg_bytes):
    """흰 배경에 렌더했을 때의 잉크 비율. 0 이면 흰색 전용판이라 카드에서 안 보인다."""
    try:
        import cairosvg
        import numpy as np
        from PIL import Image
        im = Image.open(io.BytesIO(cairosvg.svg2png(
            bytestring=svg_bytes, output_width=300, background_color="white"))).convert("L")
        return float((np.array(im) < 200).mean())
    except Exception:
        return -1.0


def main():
    dry = "--dry-run" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

    reg = {i["slug"]: i for i in json.loads(get(REG))["icons"]}
    data = json.loads((C / "brands.json").read_text())
    bl = data["brands"] if isinstance(data, dict) else data

    # 정확 일치 색인 — 부분일치는 쓰지 않는다
    known = set()
    for b in bl:
        for k in (b["id"], b.get("name_en"), b.get("name_ko"), *(b.get("aliases") or [])):
            n = norm(k)
            if n:
                known.add(n)
    ids = {b["id"] for b in bl}

    todo = []
    for slug, i in reg.items():
        if i.get("license") not in FREE:
            continue
        if norm(slug) in known or norm(i.get("title")) in known:
            continue
        bid = re.sub(r"[^a-z0-9-]", "-", slug.lower()).strip("-")
        if not bid or bid in ids:
            continue
        todo.append((bid, i))

    print(f"theSVG {len(reg):,}건 / 자유 라이선스·미보유 {len(todo):,}건", flush=True)
    if limit:
        todo = todo[:limit]
    if dry:
        for bid, i in todo[:20]:
            print(f"  {bid:<24} {i['title'][:30]:<30} {i['license']}")
        return 0

    ok = skip = fail = 0
    added = []
    for n, (bid, i) in enumerate(todo, 1):
        vs = i.get("variants") or []
        v = next((k for k in ("default", "color", "mono") if k in vs), vs[0] if vs else None)
        if not v:
            skip += 1
            continue
        try:
            b = None
            for a in range(3):
                try:
                    b = get(SVG.format(slug=i["slug"], variant=v), timeout=30)
                    break
                except Exception:
                    if a == 2:
                        raise
                    time.sleep(2 * (a + 1))
            if not b or b"<svg" not in b[:400].lower():
                raise ValueError("SVG 아님")
            # PNG 를 감싼 SVG 는 벡터가 아니다
            if b"<image" in b or b"data:image" in b:
                skip += 1
                continue
            r = ink_ratio(b)
            if 0 <= r < 0.002:
                skip += 1
                print(f"  ⬜ {bid}: 잉크 {r*100:.2f}% (빈 렌더/흰색전용)")
                continue
            d = C / bid
            d.mkdir(parents=True, exist_ok=True)
            (d / "logo.svg").write_bytes(b)
            # build-variants 는 logo.png 가 있다고 전제한다 — 없으면 PNG 가 404
            import cairosvg
            cairosvg.svg2png(bytestring=b, write_to=str(d / "logo.png"), output_width=800)
            cat = next((CAT[c] for c in (i.get("categories") or []) if c in CAT), "기타")
            added.append({
                "id": bid,
                "name_ko": i.get("title") or bid,
                "name_en": i.get("title") or bid,
                "category": cat,
                "folder": f"_clients/{bid}",
                "website": i.get("url") or "",
                "domain": re.sub(r"^https?://(www\.)?|/.*$", "", i.get("url") or ""),
                "logo_svg": "logo.svg", "has_svg": True,
                "logo_png": True, "has_png": True,
                "svg_source": "thesvg",
                "license": i.get("license"),
                "added_at": time.strftime("%Y-%m-%d"),
                "aliases": [a for a in (i.get("aliases") or []) if a],
                "sources": [{"provider": "thesvg", "file": "logo.svg",
                             "label": v, "origin_file": f"{i['slug']}/{v}.svg"}],
            })
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ❌ {bid}: {type(e).__name__}")
        if n % 100 == 0:
            print(f"  {n}/{len(todo)} · 수집 {ok}", flush=True)
        time.sleep(0.25)

    if added:
        bl.extend(added)
        (C / "brands.json").write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")))

    print(f"\n✅ 신규 등록 {ok}건 · 건너뜀 {skip}건 · 실패 {fail}건 (총 {len(bl):,}개)")
    print("   다음: build-variants.py → build-logo-variants.py → build-slim.py → sync-*-bucket.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
