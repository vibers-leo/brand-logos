#!/usr/bin/env python3
"""국내 상장사(KOSPI·KOSDAQ·KONEX) 로고를 각 회사 홈페이지에서 수집한다.

왜 이 방식인가 —
국내 브랜드는 theSVG·simple-icons 같은 공개 레지스트리에 거의 없다.
2026-08-28 실측: 카탈로그 41,618개 중 한글명 보유가 9,577개(23%)뿐이고,
상장사 2,804개 중 보유는 240개(9%)였다. 국내 이용자가 주 고객인데
정작 국내 브랜드가 비어 있다.

명단은 KRX 상장법인목록(kind.krx.co.kr)에서 받는다 — 회사명·종목코드·업종·
홈페이지가 다 들어 있는 권위 있는 원본이다. 로고는 각 사 홈페이지 헤더의
<img src="...logo...">에서 가져온다.

⚠️ 오늘까지 겪은 함정을 전부 가드로 넣었다:
  · 404 HTML 이 .svg 로 저장되는 것 — 내용을 검사한다
  · 흰색 전용 로고 — 잉크 비율 0 이면 카드에서 빈칸이 된다(송우인포텍이 그랬다)
  · 비트맵을 감싼 SVG — 벡터가 아니다
  · 16~32px 파비콘 — 로고가 아니다
  · logo.png 누락 — build-variants 가 있다고 전제해서 PNG 가 404 난다

  python3 scripts/collect-krx.py --dry-run
  python3 scripts/collect-krx.py --limit 30
  python3 scripts/collect-krx.py --workers 8
"""
import concurrent.futures as cf
import html
import io
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "_clients"
KRX = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# KRX 업종(158종) → 우리 카테고리. 접두 일치로 본다
SECTOR = [
    ("소프트웨어", "IT·테크"), ("컴퓨터", "IT·테크"), ("정보서비스", "IT·테크"),
    ("자료처리", "IT·테크"), ("반도체", "IT·테크"), ("전자부품", "IT·테크"),
    ("통신 및 방송 장비", "IT·테크"), ("전기통신", "IT·테크"),
    ("의약품", "의료·바이오"), ("의료용", "의료·바이오"), ("기초 의약물질", "의료·바이오"),
    ("자연과학 및 공학 연구", "의료·바이오"), ("병원", "의료·바이오"),
    ("금융", "금융·결제"), ("보험", "금융·결제"), ("은행", "금융·결제"), ("증권", "금융·결제"),
    ("자동차", "자동차"),
    ("화학", "에너지·화학"), ("석유", "에너지·화학"), ("전기업", "에너지·화학"),
    ("고무", "에너지·화학"), ("플라스틱", "에너지·화학"),
    ("건설", "건설·부동산"), ("부동산", "건설·부동산"), ("토목", "건설·부동산"),
    ("종합 건설", "건설·부동산"),
    ("운수", "물류·교통"), ("항공", "물류·교통"), ("해상", "물류·교통"), ("육상", "물류·교통"),
    ("창고", "물류·교통"),
    ("도매", "유통·쇼핑"), ("소매", "유통·쇼핑"), ("상품 중개", "유통·쇼핑"),
    ("음식료품", "유통·쇼핑"), ("식료품", "유통·쇼핑"), ("음료", "유통·쇼핑"),
    ("교육", "교육"),
    # 2026-08-29 보강 — 이 업종들이 매핑에 없어 292건이 '기타'로 갔다.
    # 제조업이 특히 많이 빠져 있었다(기계·철강·전기장비·정밀기기).
    ("특수 목적용 기계", "제조·그룹"), ("일반 목적용 기계", "제조·그룹"),
    ("기타 기계", "제조·그룹"), ("금속 가공", "제조·그룹"),
    ("1차 철강", "철강·중공업"), ("1차 금속", "철강·중공업"),
    ("비철금속", "철강·중공업"), ("금속 주조", "철강·중공업"),
    ("선박", "철강·중공업"), ("기타 운송장비", "철강·중공업"),
    ("전동기", "IT·테크"), ("전기장비", "IT·테크"), ("전지", "IT·테크"),
    ("측정, 시험", "IT·테크"), ("정밀기기", "IT·테크"),
    ("사진장비", "IT·테크"), ("광학", "IT·테크"),
    ("영상 및 음향", "IT·테크"), ("마그네틱", "IT·테크"),
    ("식품 제조", "식품·음료"), ("음료 제조", "식품·음료"),
    ("도축", "식품·음료"), ("과실", "식품·음료"), ("곡물", "식품·음료"),
    ("봉제의복", "뷰티·패션"), ("의복", "뷰티·패션"), ("섬유", "뷰티·패션"),
    ("가방", "뷰티·패션"), ("신발", "뷰티·패션"), ("직물", "뷰티·패션"),
    ("비료", "에너지·화학"), ("농약", "에너지·화학"), ("펄프", "에너지·화학"),
    ("종이", "에너지·화학"), ("시멘트", "건설·부동산"),
    ("건축기술", "건설·부동산"), ("엔지니어링", "건설·부동산"),
    ("부동산", "건설·부동산"),
    ("항공기", "항공·우주·방산"), ("우주선", "항공·우주·방산"),
    ("농업", "기타"), ("어업", "기타"), ("임업", "기타"),
    ("영상", "미디어·엔터"), ("오디오", "미디어·엔터"), ("출판", "미디어·엔터"),
    ("방송", "미디어·엔터"), ("광고", "미디어·엔터"), ("게임", "게임"),
]


def _decode(body, ctype=""):
    """인코딩을 맞춰 디코딩. utf-8 강제는 EUC-KR 사이트의 한글을 깨뜨린다."""
    enc = None
    m = re.search(rb'charset=["\']?([\w-]+)', body[:3000], re.I)
    if m:
        enc = m.group(1).decode("ascii", "ignore")
    for e in ([enc] if enc else []) + ["utf-8", "euc-kr", "cp949"]:
        try:
            return body.decode(e, "strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", "ignore")


def get(url, timeout=15, limit=400_000):
    r = urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout, context=CTX)
    return r.read(limit), r.headers.get("Content-Type", "")


def category(sector):
    for k, v in SECTOR:
        if sector.startswith(k) or k in sector:
            return v
    return "기타"


def fetch_list():
    """상장사 명단. **_targets/krx.json 이 있으면 그것을 쓴다.**

    ⚠️ 예전엔 항상 KRX 에서 새로 받았다. 그래서 `find-official-site.py` 로
       홈페이지 85건을 보강해 넣어도 수집기가 그걸 못 보고 계속
       no_site 로 흘렸다(2026-09-02). KRX 원본에는 홈페이지가 비어 있는
       회사가 많고, 우리가 검색으로 채운 값이 유일한 단서다.

       원본을 다시 받고 싶으면 `--refresh` 를 준다. 그때도 보강분은
       code 기준으로 살려 병합한다.
    """
    import sys as _s
    cache = Path(__file__).resolve().parent.parent / "_targets" / "krx.json"
    if cache.exists() and "--refresh" not in _s.argv:
        return json.loads(cache.read_text())
    raw, _ = get(KRX, timeout=60, limit=5_000_000)
    txt = raw.decode("euc-kr", "ignore")
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", txt, re.S):
        td = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
              for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(td) >= 9 and td[0]:
            out.append({"name": td[0], "market": td[1], "code": td[2],
                        "sector": td[3], "site": td[8]})
    # 검색으로 채운 홈페이지는 원본에 없다 — 새로 받아도 잃지 않는다
    cache = Path(__file__).resolve().parent.parent / "_targets" / "krx.json"
    if cache.exists():
        try:
            prev = {r["code"]: r for r in json.loads(cache.read_text()) if r.get("code")}
            for r in out:
                old = prev.get(r["code"])
                if old and not (r.get("site") or "").strip() and (old.get("site") or "").strip():
                    r["site"] = old["site"]
                    r["site_source"] = old.get("site_source", "merged")
        except Exception:
            pass
        cache.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return out


def ink_ratio(data, is_svg):
    """잉크 비율과 **내용이 차지하는 영역** 을 함께 잰다.

    ⚠️ 잉크 비율만으로는 부족하다. 800x129 캔버스 구석에 점만 한 마크가 있는
       이미지도 잉크 0.5% 라 '흰색 전용(0%)' 검사를 통과한다. 실제로
       에스아이리소스·엠아이텍이 그렇게 들어왔고, 애경산업은 og:image
       (1200x630 홍보 이미지)가 잡혔다 — 로고는 구석에 조그맣게 있었다.
       잉크의 **경계 상자**가 캔버스에서 차지하는 비율을 함께 본다.
    """
    try:
        import numpy as np
        from PIL import Image
        if is_svg:
            import cairosvg
            im = Image.open(io.BytesIO(cairosvg.svg2png(
                bytestring=data, output_width=300, background_color="white"))).convert("L")
        else:
            im = Image.open(io.BytesIO(data)).convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im).convert("L")
        m = np.array(im) < 200
        if not m.any():
            return 0.0, im.size, 0.0
        ys, xs = np.where(m)
        bbox = ((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)) / (im.width * im.height)
        return float(m.mean()), im.size, float(bbox)
    except Exception:
        return -1.0, (0, 0), -1.0


def pick_logo(page_html, base):
    """헤더 로고 후보를 우선순위로 고른다. SVG 를 앞에 둔다 — 원본이기 때문."""
    srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', page_html, re.I)
    srcs += re.findall(r'<source[^>]+srcset=["\']([^"\'\s]+)', page_html, re.I)
    named = [s for s in srcs if re.search(r"logo|ci[_\-.]|symbol|bi[_\-.]", s, re.I)]
    # 흰색·역상 버전은 뒤로 민다 (흰 배경에서 안 보인다)
    def rank(s):
        w = 0 if s.lower().endswith(".svg") else 1
        if re.search(r"white|wh[_\-.]|invert|reverse|dark[_\-]bg|_w\.", s, re.I): w += 4
        return w
    return [urllib.parse.urljoin(base, s) for s in sorted(named, key=rank)][:4]


def make_id(co, taken):
    """도메인에서 뽑은 읽기 쉬운 id. 없으면 종목코드."""
    d = re.sub(r"^https?://(www\.)?|/.*$", "", co["site"] or "").lower()
    base = re.sub(r"\.(co\.kr|or\.kr|kr|com|net|org)$", "", d)
    base = re.sub(r"[^a-z0-9]", "", base)
    if not base or len(base) < 2:
        base = "krx" + co["code"].lower()
    bid = base
    n = 2
    while bid in taken:
        bid = f"{base}-{n}"
        n += 1
    return bid


def work(co):
    """한 회사를 처리한다. (상태, 회사, 데이터, 확장자) 를 돌려준다."""
    site = co["site"]
    if not site:
        return ("no_site", co, None, None)
    u = site if site.startswith("http") else "http://" + site
    try:
        page, _ = get(u)
        h = _decode(page)
    except Exception as e:
        return (f"site_fail:{type(e).__name__}", co, None, None)

    for cand in pick_logo(h, u):
        try:
            data, ct = get(cand, timeout=15, limit=3_000_000)
        except Exception:
            continue
        low = data[:400].lower()
        # 404 HTML 이 이미지 경로로 오는 경우가 흔하다
        if b"<!doctype html" in low or b"<html" in low:
            continue
        is_svg = cand.lower().split("?")[0].endswith(".svg") or b"<svg" in low
        if is_svg and (b"<image" in data or b"data:image" in data):
            continue          # 비트맵을 감싼 SVG 는 벡터가 아니다
        if not is_svg and len(data) < 900:
            continue          # 파비콘 크기
        r, size, bbox = ink_ratio(data, is_svg)
        if 0 <= r < 0.002:
            continue          # 흰색 전용 — 카드에서 빈칸이 된다
        # ⚠️ 잉크가 화면을 거의 다 덮으면 로고가 아니라 **배경이 칠해진 배너**다.
        #    매드업에서 검은 네비게이션 막대(잉크 93%)를 로고로 가져왔다.
        #    진짜 로고는 24~41% 였다(채비·인벤테라·스트라드비젼 실측).
        if r > 0.80:
            continue
        # 내용이 캔버스 구석에만 몰려 있으면 로고 이미지가 아니다
        # (og:image 홍보 이미지·배너의 한 귀퉁이인 경우가 대부분)
        if 0 <= bbox < 0.05:
            continue
        if not is_svg and min(size) < 40:
            continue          # 16~32px 파비콘
        # 가로로 지나치게 긴 데다 잉크까지 많으면 배너일 확률이 높다.
        # 채비(8.7)·인벤테라(8.1) 는 정상이므로 비율만으로 자르지 않는다.
        if size[1] and size[0] / size[1] > 9 and r > 0.5:
            continue
        return ("ok", co, data, "svg" if is_svg else
                (cand.lower().split("?")[0].rsplit(".", 1)[-1][:4] or "png"))
    return ("no_logo", co, None, None)


def main():
    dry = "--dry-run" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 8

    cos = fetch_list()
    data = json.loads((C / "brands.json").read_text())
    bl = data["brands"] if isinstance(data, dict) else data

    norm = lambda s: re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())
    known = set()
    dom = set()
    ids = set()
    for b in bl:
        ids.add(b["id"])
        for k in (b.get("name_ko"), b.get("name_en"), b["id"], *(b.get("aliases") or [])):
            n = norm(k)
            if n:
                known.add(n)
        d = str(b.get("domain") or "").lower().replace("www.", "")
        if d:
            dom.add(d)

    todo = []
    for c in cos:
        d = re.sub(r"^https?://(www\.)?|/.*$", "", c["site"] or "").lower()
        if norm(c["name"]) in known or (d and d in dom):
            continue
        todo.append(c)

    print(f"상장사 {len(cos):,} · 미보유 {len(todo):,}", flush=True)
    if limit:
        todo = todo[:limit]
    if dry:
        for c in todo[:20]:
            print(f"  {c['name']:<22} {c['market']:<5} {category(c['sector']):<12} {c['site'][:40]}")
        return 0

    ok = 0
    stats = {}
    added = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for n, (st, co, blob, ext) in enumerate(ex.map(work, todo), 1):
            key = st.split(":")[0]
            stats[key] = stats.get(key, 0) + 1
            if st != "ok":
                continue
            bid = make_id(co, ids)
            ids.add(bid)
            d = C / bid
            d.mkdir(parents=True, exist_ok=True)
            is_svg = ext == "svg"
            (d / ("logo.svg" if is_svg else "logo.png")).write_bytes(blob)
            # build-variants 는 logo.png 가 있다고 전제한다 — 없으면 PNG 가 404
            # ⚠️ 예전엔 실패를 `except: pass` 로 삼켜서 has_png=true 인데 파일이
            #    없는 항목이 7건 생겼다. 실패하면 등록하지 않고 사유를 남긴다.
            if is_svg:
                try:
                    import cairosvg
                    cairosvg.svg2png(bytestring=blob, write_to=str(d / "logo.png"),
                                     output_width=800)
                except Exception as e:
                    print(f"  ❌ {bid}: PNG 변환 실패 {type(e).__name__} — 등록 안 함")
                    stats["png_fail"] = stats.get("png_fail", 0) + 1
                    import shutil
                    shutil.rmtree(d, ignore_errors=True)
                    continue
            added.append({
                "id": bid,
                "name_ko": co["name"], "name_en": co["name"],
                "category": category(co["sector"]),
                "folder": f"_clients/{bid}",
                "website": co["site"],
                "domain": re.sub(r"^https?://(www\.)?|/.*$", "", co["site"] or "").lower(),
                "logo_svg": "logo.svg" if is_svg else None,
                "has_svg": is_svg,
                "logo_png": True, "has_png": True,
                "svg_source": "krx-site",
                "krx_code": co["code"], "krx_market": co["market"],
                "krx_sector": co["sector"],
                "added_at": time.strftime("%Y-%m-%d"),
                "sources": [{"provider": "krx-site", "file": "logo.svg" if is_svg else "logo.png",
                             "origin": co["site"]}],
            })
            ok += 1
            if n % 50 == 0:
                print(f"  {n}/{len(todo)} · 수집 {ok}", flush=True)

    if added:
        bl.extend(added)
        (C / "brands.json").write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")))

    print(f"\n✅ 신규 {ok}건 (총 {len(bl):,}개)")
    print("   내역: " + " · ".join(f"{k} {v}" for k, v in sorted(stats.items())))
    print("   다음: build-variants.py → build-logo-variants.py → build-slim.py → sync-*-bucket.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
