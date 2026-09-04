#!/usr/bin/env python3
"""브라우저로 렌더한 뒤 로고를 찾는다 — 정적 HTML 로 못 잡는 것들.

정적 수집(collect-krx.py)의 실패 42%가 'no_logo' 인데, 원인을 파 보니
**정적 HTML 에 로고가 아예 없는** 경우였다:

    니어스랩        img 0개        JS 로 그리는 SPA
    기도산업        img 20 · alt 전부 빈 값
    딜리셔스        inline-svg 17  로고가 <svg> 로 직접 그려져 있다
    지에프아이       css-bg 2      CSS background-image

브라우저로 띄우면 넷 다 DOM 에서 잡힌다. 헤더 안, 화면 상단, 링크가
홈으로 가는 것을 우선한다 — 로고는 거의 항상 그 자리에 있다.

  python3 scripts/collect-krx-rendered.py --limit 20 --dry-run
  python3 scripts/collect-krx-rendered.py --limit 200
"""
import asyncio, json, os, re, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import collect_krx_lib as L
import atomic_json

BASE = Path(__file__).resolve().parent.parent
C = BASE / "_clients"

# 여러 명단에 같은 수집기를 쓴다. 상장사·공공기관·프랜차이즈는 필드 이름만
# 다를 뿐 '이름 + 홈페이지'라는 구조가 같다.
SOURCES = {
    "krx": {"file": "krx.json", "name": "name", "src": "krx-rendered",
            "kind": None, "cat": None},
    "gov": {"file": "gov.json", "name": "name", "src": "gov-rendered",
            "kind": "공공기관", "cat": "공공·기관"},
    "franchise": {"file": "franchise.json", "name": "brand", "src": "franchise-rendered",
                  "kind": "프랜차이즈", "cat": "식품·음료"},
    # 미보유 목록(collect-wanted). 카테고리가 브랜드마다 달라
    # cat 을 고정하지 않고 타겟의 `cat` 을 그대로 쓴다.
    "wanted": {"file": "wanted.json", "name": "name", "src": "wanted-rendered",
               "kind": None, "cat": None},
}
SRC = SOURCES[sys.argv[sys.argv.index("--source") + 1]] if "--source" in sys.argv else SOURCES["krx"]
TARGETS = BASE / "_targets" / SRC["file"]
NAMEK = SRC["name"]
# ⚠️ playwright 캐시의 실행 파일 경로는 버전마다 다르다. 하드코딩하면
#    'executable doesn\'t exist' 로 죽는다(2026-09-02). 있는 것을 찾아 쓴다.
def _find_browser():
    import glob
    pats = [
        str(Path.home() / "Library/Caches/ms-playwright/chromium_headless_shell-*/"
                          "chrome-headless-shell-mac-*/chrome-headless-shell"),
        str(Path.home() / "Library/Caches/ms-playwright/chromium-*/"
                          "chrome-mac*/Chromium.app/Contents/MacOS/Chromium"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        # GitHub Actions(리눅스) — playwright install chromium 이 두는 곳
        str(Path.home() / ".cache/ms-playwright/chromium_headless_shell-*/chrome-linux/headless_shell"),
        str(Path.home() / ".cache/ms-playwright/chromium-*/chrome-linux/chrome"),
    ]
    for pat in pats:
        for f in sorted(glob.glob(pat), reverse=True):
            if os.access(f, os.X_OK):
                return f
    return None

EXE = _find_browser()

# 페이지 안에서 로고 후보를 고르는 규칙. 브라우저가 이미 계산한 좌표·크기를
# 쓸 수 있어 정적 파싱보다 훨씬 정확하다.
JS = r"""
() => {
  const out = [];
  const push = (kind, src, el, why) => {
    const r = el.getBoundingClientRect();
    if (r.width < 24 || r.height < 12) return;          // 아이콘 부스러기
    if (r.top > 400) return;                            // 화면 상단만
    out.push({kind, src, w: Math.round(r.width), h: Math.round(r.height),
              top: Math.round(r.top), left: Math.round(r.left), why});
  };
  const inHeader = el => !!el.closest('header,#header,.header,nav,.gnb,#gnb,.navbar,.top,.tit_logo,h1');
  const homeLink = el => { const a = el.closest('a'); if (!a) return false;
    try { const u = new URL(a.href, location.href);
      return u.origin === location.origin && (u.pathname === '/' || /index\.(html?|php|asp)$/i.test(u.pathname)); }
    catch { return false; } };

  for (const img of document.images) {
    const s = img.currentSrc || img.src; if (!s) continue;
    let why = null;
    if (/logo|ci[_\-.]|symbol|bi[_\-.]/i.test(s)) why = 'filename';
    else if (img.alt && /로고|심볼|엠블럼|마크|logo|symbol/i.test(img.alt)) why = 'alt';
    else if (homeLink(img)) why = 'homelink';
    else if (inHeader(img)) why = 'header';
    if (why) push('img', s, img, why);
  }
  // inline <svg> — 문서에 직접 그려진 로고
  for (const svg of document.querySelectorAll('svg')) {
    if (!(inHeader(svg) || homeLink(svg))) continue;
    const box = svg.getBoundingClientRect();
    if (box.width < 40 || box.height < 16) continue;
    const clone = svg.cloneNode(true);
    if (!clone.getAttribute('xmlns')) clone.setAttribute('xmlns','http://www.w3.org/2000/svg');
    if (!clone.getAttribute('viewBox') && box.width && box.height)
      clone.setAttribute('viewBox', `0 0 ${box.width} ${box.height}`);
    push('inline-svg', clone.outerHTML, svg, inHeader(svg) ? 'header' : 'homelink');
  }
  // CSS background-image
  for (const el of document.querySelectorAll('header *,nav *,.logo,.gnb *,h1 *,h1')) {
    const bg = getComputedStyle(el).backgroundImage;
    const m = bg && bg.match(/url\(["']?([^"')]+)/);
    if (m) push('css', new URL(m[1], location.href).href, el, 'css-bg');
  }
  return out;
}
"""

RANK = {"filename": 0, "alt": 1, "homelink": 2, "header": 3, "css-bg": 4}

# collect-krx.py 의 가드를 그대로 쓴다 — 두 벌로 갈리면 한쪽만 고쳐지고
# 다른 쪽으로 배너·파비콘이 새어 들어온다.
import importlib.util as _il
_spec = _il.spec_from_file_location("ckrx", Path(__file__).resolve().parent / "collect-krx.py")
_ckrx = _il.module_from_spec(_spec)
_sys_argv = sys.argv
sys.argv = ["collect-krx.py", "--dry-run", "--limit", "0"]   # main() 이 즉시 반환하도록
try:
    _spec.loader.exec_module(_ckrx)
finally:
    sys.argv = _sys_argv


def accept(data, is_svg):
    """collect-krx 와 똑같은 기준. 통과하면 True."""
    low = data[:400].lower()
    if b"<!doctype html" in low or b"<html" in low:
        return False, "HTML 응답"
    if is_svg and (b"<image" in data or b"data:image" in data):
        return False, "비트맵 감싼 SVG"
    if not is_svg and len(data) < 900:
        return False, "파비콘 크기"
    r, size, bbox = L.ink_ratio(data, is_svg)
    if r < 0:
        return False, "렌더 실패·문장·사진"
    if r < 0.002:
        # ⚠️ '흰색 전용'은 버릴 게 아니다. 다크 배경용 흰 로고는 정상이고
        #    우리는 logo-white 를 자동 생성하므로 값어치가 있다.
        #    잉크 비율은 **흰 배경 기준**이라 흰 로고를 0 으로 본다.
        #    알파 채널로 다시 재면 색과 무관하게 내용 유무를 알 수 있다.
        o = _opaque_ratio(data, is_svg)
        if o is None or o < 0.01:
            return False, "빈 이미지"
        if o > 0.92:
            return False, "전면 불투명(사각형)"
        # 흰 로고 경로로도 UI 아이콘이 샌다 — 흰 지구본이 그렇게 들어왔다.
        if size[0] and size[1] and 0.85 < size[0] / size[1] < 1.18:
            return False, f"정사각 단색(흰색) — UI 아이콘 의심 {size[0]}x{size[1]}"
        return True, f"흰색 로고 (불투명 {o:.2f}) {size[0]}x{size[1]}"
    if r > 0.80:
        return False, f"통짜 배너(잉크 {r:.2f})"
    if 0 <= bbox < 0.05:
        return False, "구석에만 내용"
    # ⚠️ **정사각 단색 픽토그램은 UI 아이콘이다.** 지구본·돋보기·장바구니·
    #    햄버거 메뉴·플러스·외부링크가 로고 자리에 들어왔다(2026-09-02, 12건).
    #    로고는 대개 가로로 길고 색이 둘 이상이다. 정사각이면서 색이 하나뿐이면
    #    거른다 — 진짜 단색 정사각 로고는 드물고, 잘못 넣는 것보다 놓치는 게 낫다.
    if size[0] and size[1]:
        ar = size[0] / size[1]
        if 0.85 < ar < 1.18:
            nc = _color_count(data, is_svg)
            if nc is not None and nc <= 2:
                return False, f"정사각 단색 픽토그램(색 {nc}종) — UI 아이콘"
    # ⚠️ min(size)<40 은 **가로형 로고를 죽인다** — 198x24 가 그렇게 탈락했다.
    #    로고는 높이가 낮은 게 정상이다. 폭·높이·면적을 따로 본다.
    if not is_svg and (size[0] < 48 or size[1] < 14 or size[0] * size[1] < 2000):
        return False, f"너무 작음 {size}"
    if size[1] and size[0] / size[1] > 9 and r > 0.5:
        return False, "가로로 긴 배너"
    return True, f"잉크 {r:.2f} {size[0]}x{size[1]}"


def _color_count(data, is_svg):
    """불투명 픽셀의 색 종류 수. UI 아이콘은 1~2종이다."""
    import io as _io
    from PIL import Image
    import numpy as np
    try:
        if is_svg:
            import cairosvg, safesvg
            png = cairosvg.svg2png(
                bytestring=safesvg.sanitize(safesvg.inline_internal_entities(data)),
                output_width=120)
            im = Image.open(_io.BytesIO(png)).convert("RGBA")
        else:
            im = Image.open(_io.BytesIO(data)).convert("RGBA")
            im.thumbnail((120, 120))
        a = np.array(im)
        op = a[..., 3] > 40
        if op.sum() < 30:
            return None
        # 16단계로 뭉뚱그려 안티앨리어싱을 색으로 세지 않는다
        q = (a[..., :3][op] // 48) * 48
        return len(np.unique(q, axis=0))
    except Exception:
        return None


def _opaque_ratio(data, is_svg):
    """알파 채널로 내용 유무를 잰다. 색과 무관하다."""
    import io as _io
    from PIL import Image
    import numpy as np
    try:
        if is_svg:
            import cairosvg, safesvg
            png = cairosvg.svg2png(
                bytestring=safesvg.sanitize(safesvg.inline_internal_entities(data)),
                output_width=200)
            im = Image.open(_io.BytesIO(png)).convert("RGBA")
        else:
            im = Image.open(_io.BytesIO(data)).convert("RGBA")
            im.thumbnail((200, 200))
    except Exception:
        return None
    return float((np.array(im)[..., 3] > 24).mean())


def fetch_candidate(top, page_url):
    """후보 하나를 실제 바이트로. (data, ext) 또는 (None, 사유)"""
    if top["kind"] == "inline-svg":
        return top["src"].encode(), "svg"
    try:
        data, _ = L.get(top["src"], timeout=15, limit=3_000_000)
    except Exception as e:
        return None, f"받기 실패 {type(e).__name__}"
    is_svg = top["src"].lower().split("?")[0].endswith(".svg") or b"<svg" in data[:400].lower()
    return data, ("svg" if is_svg else
                  (top["src"].lower().split("?")[0].rsplit(".", 1)[-1][:4] or "png"))

async def probe(pg, url):
    """⚠️ 두 가지 때문에 처음엔 전부 실패했다(2026-09-02):
       · ERR_NAME_NOT_RESOLVED — 명단의 www 도메인이 죽은 경우가 있다.
         www 를 떼거나 https 로 바꿔 다시 시도한다.
       · "interrupted by another navigation" — 사이트가 스스로 리다이렉트하는데
         goto 가 그걸 실패로 본다. 흔한 일이라 무시하고 렌더 결과를 읽는다.
    """
    tries = [url]
    m = re.match(r"^(https?)://(www\.)?(.+)$", url)
    if m:
        sch, _, rest = m.groups()
        for alt in (f"https://{rest}", f"http://{rest}",
                    f"https://www.{rest}", f"http://www.{rest}"):
            if alt not in tries:
                tries.append(alt)
    last = ""
    for u in tries[:4]:
        try:
            await pg.goto(u, timeout=25000, wait_until="domcontentloaded")
        except Exception as e:
            msg = str(e)
            last = f"{type(e).__name__}: {msg[:70]}"
            # 리다이렉트로 끊긴 것은 실패가 아니다 — 페이지는 떠 있다
            if "interrupted by another navigation" not in msg:
                continue
        try:
            await pg.wait_for_timeout(1200)      # JS 렌더 여유
            rows = await pg.evaluate(JS)
            break
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:70]}"
    else:
        return None, last or "접속 실패"
    try:
        pass
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:90]}"
    if not rows:
        return [], "후보 없음"
    # 왼쪽 위에 있고 신호가 강한 것 우선
    rows.sort(key=lambda r: (RANK.get(r["why"], 9), r["top"], r["left"]))
    return rows, f"{len(rows)}개"

async def main():
    dry = "--dry-run" in sys.argv
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 20
    rows = json.loads(TARGETS.read_text())
    d = json.loads((C / "brands.json").read_text())["brands"]
    norm = lambda s: re.sub(r"[^가-힣a-z0-9]", "", str(s or "").lower())
    known = {norm(b.get("name_ko")) for b in d} | {norm(b.get("name_en")) for b in d}
    dom = {str(b.get("domain") or "").lower().replace("www.", "") for b in d}
    todo = [x for x in rows
            if norm(x[NAMEK]) not in known and (x.get("site") or "").strip()
            and re.sub(r"^https?://(www\.)?|/.*$", "", x["site"]).lower() not in dom]
    todo = todo[:limit]
    print(f"  렌더 대상 {len(todo)}곳", flush=True)

    from playwright.async_api import async_playwright
    hit = miss = 0
    async with async_playwright() as p:
        if not EXE:
            print("⛔ 브라우저를 찾을 수 없다 — playwright install chromium"); return
        br = await p.chromium.launch(executable_path=EXE, headless=True)
        ctx = await br.new_context(viewport={"width": 1440, "height": 900},
                                   user_agent=L.UA)
        pg = await ctx.new_page()
        doc = json.loads((C / "brands.json").read_text())
        bl = doc["brands"] if isinstance(doc, dict) else doc
        ids = {b["id"] for b in bl}
        # ⚠️ 프랜차이즈는 한 본사가 여러 브랜드를 갖고 **같은 사이트를 쓴다**.
        #    한솔교육 지사 4개가 전부 hs_logo.png 를 가리켰다. 그대로 등록하면
        #    같은 로고 카드가 네 장 생긴다. 이번 회차 안에서 중복을 막는다.
        import hashlib as _h
        seen_logo = set()
        import time as _t
        added = []
        for x in todo:
            got, why = await probe(pg, x["site"])
            if got is None:
                print(f"   {x[NAMEK][:14]:<16} 접속❌ {why[:44]}"); miss += 1; continue
            if not got:
                print(f"   {x[NAMEK][:14]:<16} — {why}"); miss += 1; continue
            # 후보를 순서대로 시도해 가드를 통과하는 첫 것을 쓴다
            chosen = None
            reasons = []
            for top in got[:5]:
                data, ext = fetch_candidate(top, x["site"])
                if data is None:
                    reasons.append(f"{top['why']}:{ext}"); continue
                ok_, note = accept(data, ext == "svg")
                if ok_:
                    chosen = (top, data, ext, note); break
                reasons.append(f"{top['why']}:{note}")
            if not chosen:
                print(f"   {x[NAMEK][:14]:<16} — 탈락 {' | '.join(reasons[:3])}"); miss += 1; continue
            top, data, ext, note = chosen
            sig = _h.sha1(data).hexdigest()[:16]
            if sig in seen_logo:
                print(f"   {x[NAMEK][:14]:<16} — 같은 로고 중복(이번 회차)"); miss += 1; continue
            seen_logo.add(sig)
            label = f"<svg>{top['w']}x{top['h']}" if top["kind"] == "inline-svg" else top["src"].split("/")[-1][:30]
            print(f"   {x[NAMEK][:14]:<16} ✅ [{top['why']}] {label}  {note}")
            hit += 1
            if dry:
                continue
            bid = _ckrx.make_id({"site": x.get("site",""), "code": x.get("code") or x.get("reg") or ""}, ids); ids.add(bid)
            d = C / bid; d.mkdir(parents=True, exist_ok=True)
            # ⚠️ **수집 출처를 폴더에 남긴다.** brands.json 은 여러 프로세스가
            #    함께 쓰다가 덮어써질 수 있는데(2026-09-02 공공기관 25건이 그렇게
            #    사라졌다), 이 파일이 있으면 폴더만으로 되살릴 수 있다.
            #    홈페이지 주소가 특히 중요하다 — 그게 없으면 어느 브랜드인지
            #    알 수 없어 복구 자체가 불가능하다.
            (d / "_source.json").write_text(json.dumps({
                "id": bid,
                "name": x[NAMEK],
                "site": x.get("site", ""),
                "source": SRC["src"],
                "logo_url": top["src"][:400] if top["kind"] != "inline-svg" else "(inline-svg)",
                "found_by": top["why"],
                "collected_at": _t.strftime("%Y-%m-%d %H:%M"),
                **{k: v for k, v in x.items() if k in
                   ("code", "market", "sector", "wikidata", "kind", "hq", "reg")},
            }, ensure_ascii=False, indent=1))
            is_svg = ext == "svg"
            (d / ("logo.svg" if is_svg else "logo.png")).write_bytes(data)
            if is_svg:
                # ⚠️ 실패를 삼키면 has_png=true 인데 파일이 없는 항목이 생긴다.
                try:
                    import cairosvg, safesvg
                    cairosvg.svg2png(
                        bytestring=safesvg.sanitize(safesvg.inline_internal_entities(data)),
                        write_to=str(d / "logo.png"), output_width=800)
                except Exception as e:
                    print(f"      ❌ PNG 변환 실패 {type(e).__name__} — 등록 안 함")
                    import shutil; shutil.rmtree(d, ignore_errors=True)
                    hit -= 1; miss += 1; continue
            added.append({
                "id": bid, "name_ko": x[NAMEK], "name_en": x[NAMEK],
                "category": SRC["cat"] or x.get("cat") or _ckrx.category(x.get("sector", "")),
                "folder": f"_clients/{bid}", "website": x["site"],
                "domain": re.sub(r"^https?://(www\.)?|/.*$", "", x["site"] or "").lower(),
                "logo_svg": "logo.svg" if is_svg else None, "has_svg": is_svg,
                "logo_png": True, "has_png": True,
                "svg_source": SRC["src"],
                "origin": "KR",
                **({"kr_kind": SRC["kind"]} if SRC["kind"] else {}),
                **({"krx_code": x.get("code"), "krx_market": x.get("market"),
                    "krx_sector": x.get("sector")} if x.get("code") else {}),
                **({"wikidata": x["wikidata"]} if x.get("wikidata") else {}),
                "added_at": _t.strftime("%Y-%m-%d"),
            })
        await br.close()
    print(f"\n  후보 확보 {hit} · 실패 {miss}  ({hit/max(1,hit+miss)*100:.0f}%)")
    if added and not dry:
        # ⚠️ 시작할 때 읽은 스냅샷에 덧붙여 저장하면, 그 사이 **다른 수집기가
        #    등록한 브랜드를 통째로 지운다.** 2026-09-02 에 프랜차이즈 수집이
        #    공공기관 25건을 그렇게 날렸다.
        #    저장 직전에 **다시 읽어** 병합한다. id 기준으로 겹치면 기존을 남긴다.
        # 락으로 read-modify-write 전체를 감싼다 (덮어쓰기 방지)
        with atomic_json.locked(C / "brands.json"):
            fresh = json.loads((C / "brands.json").read_text())
            cur = fresh["brands"] if isinstance(fresh, dict) else fresh
            have = {b["id"] for b in cur}
            merged = 0
            for r in added:
                if r["id"] in have:
                    continue
                cur.append(r); have.add(r["id"]); merged += 1
            if isinstance(fresh, dict):
                fresh["brands"] = cur; fresh["total"] = len(cur)
            atomic_json.write_json(C / "brands.json", fresh if isinstance(fresh, dict) else cur)
        bl = cur
        if merged != len(added):
            print(f"  ℹ️ {len(added) - merged}건은 그 사이 다른 수집기가 이미 등록")
        added = added[:merged] if merged else []
        print(f"  ✅ 신규 {len(added)}건 등록 (총 {len(bl):,})")
        print("  다음: build-variants.py → build-logo-variants.py → build-slim.py → sync-bucket.sh")

# ⚠️ 가드가 없으면 **import 만 해도 수집이 통째로 돈다.**
#    upgrade-to-svg.py 가 추출 함수를 재사용하려고 import 했다가
#    KRX 수집이 한 회차 돌아 브랜드가 등록됐다 (2026-09-03).
if __name__ == "__main__":
    asyncio.run(main())
