#!/usr/bin/env python3
"""CI/BI 소개 페이지에서 **원본 벡터(.ai/.eps/.pdf/.svg/.zip)** 를 찾아 logo.svg 로 만든다.

국내 사이트의 <img> 로고는 거의 PNG 다. 하지만 대학·지자체·공기업·협회는 'CI 소개',
'상징', '브랜드', '홍보자료' 페이지에 일러스트레이터 원본을 공개한다. 그 링크를 따라간다.
PNG 만 있는 국내 브랜드(1,851곳)가 대상이며, 서비스 가치는 진짜 벡터 비율이 정한다.

  python3 scripts/collect-ci-page.py --limit 20 --dry-run     # 링크만 찾아 보고
  python3 scripts/collect-ci-page.py --limit 50               # 받아서 변환·승격
  python3 scripts/collect-ci-page.py --ids busan,kfcc        # 특정 브랜드

변환: .ai/.pdf → pdftocairo -svg (1페이지) · .eps → gs → pdf → svg · .zip → 안의 svg/ai/eps
검증: safesvg 정규화 후 cairosvg 렌더, 잉크 0.5%~ · 비트맵 내장 SVG 는 벡터로 치지 않는다.
"""
import sys, json, re, asyncio, argparse, io, subprocess, tempfile, zipfile, time, urllib.request
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
C, T = BASE / "_clients", BASE / "_targets"
sys.path.insert(0, str(BASE / "scripts"))
import atomic_json, safesvg

LINK_TXT = re.compile(r"(?<![A-Za-z])(CI|BI|UI)(?![A-Za-z])|심볼|상징|로고|엠블럼|브랜드|홍보\s*자료|아이덴티티|Identity|Brand\b|Logo\b|Symbol\b", re.I)
LINK_HREF = re.compile(r"/(ci|bi|symbol|logo|brand|identity|emblem|intro|about|pr|promotion)[/._-]?", re.I)
FILE_EXT = re.compile(r"\.(ai|eps|svg|pdf|zip)(\?|$)", re.I)
FILE_HINT = re.compile(r"\bci\b|\bbi\b|logo|symbol|emblem|심볼|로고|엠블럼|상징|brand|signature|워드마크|wordmark|identity", re.I)
# 캠페인·포스터·서식·공고 zip/pdf 가 '다운로드' 속성만으로 걸려 오탐이 났다(2026-09-06 기상청 summer_campaign.zip)
FILE_NEG  = re.compile(r"campaign|poster|포스터|안내|신청|서식|공고|보도|leaflet|리플렛|브로슈어|brochure|banner|배너|typhoon|heatwave|캠페인", re.I)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
TRIED_F = T / ".ci-tried.json"

JS_LINKS = r"""
() => [...document.querySelectorAll('a[href]')].map(a => {
  // 인라인 SVG 안의 <a> 는 a.href 가 SVGAnimatedString(객체)다 — 문자열로 정규화(2026-09-06 TypeError)
  let h = a.getAttribute('href') || '';
  try { h = new URL(h, location.href).href; } catch (e) { h = String(a.href && a.href.baseVal || a.href || ''); }
  return { href: String(h), text: (a.innerText||a.getAttribute('title')||a.getAttribute('aria-label')||'').trim().slice(0,60),
           dl: a.hasAttribute('download') };
})
"""

def same_site(u, home):
    h = lambda x: re.sub(r"^https?://(www\.)?|/.*$", "", x).lower()
    return h(u) == h(home) or h(u).endswith("." + h(home)) or h(home).endswith("." + h(u))

DL_TXT = re.compile(r"다운로드|download|\bAI\b|\bEPS\b|\bSVG\b|원본|일러스트|벡터|vector", re.I)
DL_HREF = re.compile(r"download|filedown|fileDown|atchFile|downloadRun|getFile|fileId|attach", re.I)

def fetch(url, limit=40*1024*1024):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": url})
    with urllib.request.urlopen(req, timeout=40) as r:
        data = r.read(limit + 1)
        cd = r.headers.get("Content-Disposition", "")
    if len(data) > limit: raise ValueError("파일이 40MB 초과")
    return data, cd

def sniff_ext(data: bytes, cd: str, href: str) -> str | None:
    """매직바이트 → ai/pdf/eps/svg/zip. 확장자 없는 CMS 다운로드 링크를 위해."""
    h = data[:16]
    if h.startswith(b"%PDF"): return "pdf"          # .ai 도 PDF 호환이라 pdf 로 처리해도 같다
    if h.startswith(b"%!PS") or h[:4] == b"\xc5\xd0\xd3\xc6": return "eps"
    if h.startswith(b"PK"): return "zip"
    if b"<svg" in data[:4000] or (h.lstrip()[:5] == b"<?xml" and b"<svg" in data[:20000]): return "svg"
    m = re.search(r"\.(ai|eps|svg|pdf|zip)\b", cd + " " + href, re.I)
    return m.group(1).lower() if m else None

def to_svg(data: bytes, ext: str, work: Path) -> bytes | None:
    """원본 바이트 → SVG 바이트. 실패하면 None."""
    ext = ext.lower()
    if ext == "svg":
        return data
    if ext == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [n for n in z.namelist() if not n.startswith("__MACOSX") and FILE_EXT.search(n) and not n.lower().endswith(".zip")]
            # 로고답게 이름 붙은 것 우선, svg > ai > eps > pdf
            pri = {"svg": 0, "ai": 1, "eps": 2, "pdf": 3}
            names.sort(key=lambda n: (0 if FILE_HINT.search(Path(n).stem) else 1, pri.get(Path(n).suffix[1:].lower(), 9), len(n)))
            for n in names[:6]:
                out = to_svg(z.read(n), Path(n).suffix[1:], work)
                if out: return out
        return None
    src = work / f"src.{ext}"
    src.write_bytes(data)
    if ext == "eps":
        pdf = work / "src.pdf"
        r = subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dEPSCrop", "-sDEVICE=pdfwrite", f"-sOutputFile={pdf}", str(src)],
                           capture_output=True, timeout=60)
        if r.returncode != 0 or not pdf.exists(): return None
        src = pdf
    # ai/pdf → 첫 페이지 svg
    out = work / "out.svg"
    r = subprocess.run(["pdftocairo", "-svg", "-f", "1", "-l", "1", str(src), str(out)], capture_output=True, timeout=60)
    if r.returncode != 0 or not out.exists(): return None
    return out.read_bytes()

def good_vector(svg: bytes) -> tuple[bool, str]:
    head = svg[:8000].decode("utf-8", "ignore")
    if "<svg" not in head: return False, "SVG 아님"
    if "<image" in head or "data:image/" in head: return False, "비트맵 내장"
    if len(svg) > 6_000_000: return False, "6MB 초과"
    try:
        import cairosvg
        from PIL import Image
        import numpy as np
        from scipy import ndimage
        png = cairosvg.svg2png(bytestring=safesvg.sanitize(safesvg.inline_internal_entities(svg)), output_width=400)
        a = np.array(Image.open(io.BytesIO(png)).convert("RGBA"))
        al = a[..., 3] > 20
        ink = al.mean()
        if ink < 0.005: return False, f"빈 렌더 {ink:.1%}"
        # ⚠️ CI 매뉴얼 '한 페이지'가 통째로 나오는 경우 — 잉크가 적고 덩어리가 여럿이다
        #    (2026-09-06 부산가톨릭대: 잉크 3%, 작은 심볼 3개). 로고 하나가 아니라 시트다.
        lab, n = ndimage.label(ndimage.binary_dilation(al, iterations=6))
        sizes = sorted((lab == i).sum() for i in range(1, n + 1)) if n else []
        big = [x for x in sizes if x > al.size * 0.004]
        if ink < 0.08 or len(big) >= 3:
            return False, f"시트 의심(잉크 {ink:.0%}·덩어리 {len(big)})"
        return True, f"잉크 {ink:.0%}"
    except Exception as e:
        return False, f"렌더 실패 {type(e).__name__}"

async def run(a):
    raw = json.loads((C / "brands.json").read_text()); br = raw["brands"] if isinstance(raw, dict) else raw
    tried = json.loads(TRIED_F.read_text()) if TRIED_F.exists() else {}
    only = set(a.ids.split(",")) if a.ids else None
    pool = [b for b in br if b.get("origin") == "KR" and not b.get("has_svg") and not b.get("hidden")
            and (b.get("website") or b.get("domain")) and (not only or b["id"] in only)]
    # 공공기관·대학·지자체 먼저 — CI 페이지가 있을 확률이 높다
    if a.kind:
        pool = [b for b in pool if b.get("kr_kind") == a.kind]
    pri = {"대학": 0, "지자체": 0, "공공기관": 1, "고등학교": 2, "병원": 2, "언론사": 2, "금융사": 2, "스포츠구단": 2}
    # 지방○○청·○○지청 같은 하부기관은 CI 가 본청 것이라 후순위
    sub_office = re.compile(r"지방|지청|출장소|사업소|지역본부|지사$")
    pool.sort(key=lambda b: (pri.get(b.get("kr_kind"), 3), 1 if sub_office.search(b.get("name_ko") or "") else 0))
    if not only:
        pool = [b for b in pool if b["id"] not in tried]
    pool = pool[: a.limit]
    print(f"대상 {len(pool)}곳 (PNG-only 국내 · 시도 안 한 것)\n", flush=True)

    from playwright.async_api import async_playwright
    hit = 0; found_any = 0; promoted = []
    async with async_playwright() as p:
        # ⚠️ playwright 캐시의 실행 파일 경로는 버전마다 달라 기본 launch 가 'Executable doesn't exist' 로
        #    죽는다(2026-09-06). 있는 것을 찾아 쓰고, 없으면(러너) 내장 크로미움으로.
        import glob, os
        exe = None
        for pat in (str(Path.home() / "Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac-*/chrome-headless-shell"),
                    str(Path.home() / "Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"),
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
            m = sorted(glob.glob(pat), reverse=True)
            if m and os.access(m[0], os.X_OK): exe = m[0]; break
        br_ = await p.chromium.launch(**({"executable_path": exe} if exe else {}), headless=True)
        ctx = await br_.new_context(user_agent=UA, viewport={"width": 1366, "height": 900})
        pg = await ctx.new_page()
        for b in pool:
            home = b.get("website") or f"https://{b['domain']}"
            name = (b.get("name_ko") or b["id"])[:12]
            note = ""
            try:
                await pg.goto(home, wait_until="domcontentloaded", timeout=25000)
                await pg.wait_for_timeout(800)
                links = await pg.evaluate(JS_LINKS)
            except Exception as e:
                tried[b["id"]] = {"at": time.strftime("%Y-%m-%d"), "why": f"접속❌ {type(e).__name__}"}
                print(f"   {name:<14} 접속❌ {type(e).__name__}", flush=True); continue
            def _ok_file(l):
                blob = l["href"] + " " + l["text"]
                if FILE_NEG.search(blob): return False
                m = FILE_EXT.search(l["href"])
                if m:
                    ext = m.group(1).lower()
                    if ext in ("ai", "eps", "svg"): return True      # 벡터 포맷은 그 자체가 신호
                    return bool(FILE_HINT.search(blob))              # zip/pdf 는 로고 힌트가 있어야
                # 확장자 없는 CMS 다운로드(downloadRun.do?qcode=…) — 텍스트에 다운로드/AI/원본이 있어야
                return bool(DL_HREF.search(l["href"]) and (DL_TXT.search(l["text"]) or FILE_HINT.search(blob)))
            files = [l for l in links if _ok_file(l)]
            cands = [l for l in links if same_site(l["href"], home) and (LINK_TXT.search(l["text"]) or LINK_HREF.search(l["href"]))
                     and not FILE_EXT.search(l["href"])]
            # 홈에 직접 파일이 없으면 CI 페이지 후보 3개까지 들어가 본다
            seen = set(); visited = 0
            for l in cands:
                if files or visited >= 3: break
                if l["href"] in seen: continue
                seen.add(l["href"]); visited += 1
                try:
                    await pg.goto(l["href"], wait_until="domcontentloaded", timeout=20000)
                    await pg.wait_for_timeout(600)
                    sub = await pg.evaluate(JS_LINKS)
                    files = [x for x in sub if _ok_file(x)]
                    if files: note = f"via {l['text'][:14] or l['href'][-24:]}"
                except Exception:
                    continue
            if not files:
                tried[b["id"]] = {"at": time.strftime("%Y-%m-%d"), "why": f"CI 파일 없음 (페이지 {visited}곳)"}
                print(f"   {name:<14} — CI 파일 없음 (후보 페이지 {visited})", flush=True); continue
            found_any += 1
            pri_ext = {"svg": 0, "ai": 1, "eps": 2, "zip": 3, "pdf": 4}
            def _ext_of(l):
                m = FILE_EXT.search(l["href"]); return m.group(1).lower() if m else "?"
            files.sort(key=lambda l: pri_ext.get(_ext_of(l), 5))
            if a.dry_run:
                print(f"   {name:<14} 🔎 {len(files)}개 {note}  {[_ext_of(f) for f in files[:5]]}  {files[0]['text'][:16]} {files[0]['href'][-50:]}", flush=True)
                continue
            got = None
            svg = None; why = ""     # ⚠️ 브랜드마다 초기화 — 앞 브랜드의 svg 가 새어 들어가 단국대 큐에 충북대 시트가 들어갔다(2026-09-06)
            # '다운로드' 링크가 파일이 아니라 **다운로드 페이지**인 경우(단국대 /ui_download) 한 단계 더 들어간다
            extra = []
            for f in list(files[:5]):
                if FILE_EXT.search(f["href"]): continue
                try:
                    await pg.goto(f["href"], wait_until="domcontentloaded", timeout=20000)
                    await pg.wait_for_timeout(500)
                    sub = await pg.evaluate(JS_LINKS)
                    extra += [x for x in sub if _ok_file(x) and x["href"] != f["href"]]
                except Exception:
                    pass
            seen_h = {f["href"] for f in files}
            files += [x for x in extra if x["href"] not in seen_h]
            files.sort(key=lambda l: pri_ext.get(_ext_of(l), 5))
            for f in files[:8]:
                try:
                    data, cd = fetch(f["href"])
                except Exception:
                    continue
                ext = sniff_ext(data, cd, f["href"])
                if not ext: continue
                with tempfile.TemporaryDirectory() as td:
                    svg = to_svg(data, ext, Path(td))
                if not svg: continue
                ok, why = good_vector(svg)
                if ok:
                    got = (f, ext, data, svg, why); break
            if not got:
                # 변환은 됐는데 시트로 의심되는 것은 버리지 않고 검토 큐에 둔다 — 사람이 viewBox 크롭으로 살릴 수 있다
                if svg and "시트 의심" in why:
                    q = C / "_svg-review"; q.mkdir(exist_ok=True); (q / f"{b['id']}.svg").write_bytes(svg)
                    tried[b["id"]] = {"at": time.strftime("%Y-%m-%d"), "why": f"검토큐 {why}"}
                    print(f"   {name:<14} 🔎 검토큐 ({why})", flush=True); continue
                tried[b["id"]] = {"at": time.strftime("%Y-%m-%d"), "why": "파일은 있는데 변환·검증 실패"}
                print(f"   {name:<14} — 파일 {len(files)}개 있으나 변환 실패", flush=True); continue
            f, ext, data, svg, why = got
            d = C / b["id"]; (d / "sources" / "ci").mkdir(parents=True, exist_ok=True)
            (d / "sources" / "ci" / (re.sub(r"[^A-Za-z0-9._-]", "_", f["href"].split("/")[-1].split("?")[0])[:80] or f"ci.{ext}")).write_bytes(data)
            (d / "logo.svg").write_bytes(svg)
            promoted.append(b["id"]); hit += 1
            print(f"   {name:<14} ✅ {ext.upper()} → SVG {why} {note}", flush=True)
        await br_.close()
    if not a.dry_run:
        TRIED_F.write_text(json.dumps(tried, ensure_ascii=False, indent=0) + "\n")
    print(f"\n  CI 파일 발견 {found_any} · SVG 승격 {hit} / {len(pool)}")
    if promoted and not a.dry_run:
        with atomic_json.locked(C / "brands.json"):
            raw = json.loads((C / "brands.json").read_text()); br = raw["brands"] if isinstance(raw, dict) else raw
            s = set(promoted)
            for b in br:
                if b["id"] in s:
                    b["has_svg"] = True; b["logo_svg"] = "logo.svg"; b["svg_from"] = "ci-page"
            if isinstance(raw, dict): raw["brands"] = br
            atomic_json.write_json(C / "brands.json", raw if isinstance(raw, dict) else br)
        print(f"  다음: for b in {' '.join(promoted[:5])}...; do python3 build-variants.py --force --brand $b; done")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ids")
    ap.add_argument("--kind", help="kr_kind 필터 (대학·지자체·공공기관…)")
    asyncio.run(run(ap.parse_args()))
