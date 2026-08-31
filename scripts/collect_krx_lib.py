#!/usr/bin/env python3
"""국내 사이트에서 로고를 뽑을 때 쓰는 공용 함수.

collect-krx.py(상장사)와 collect-kr-institutions.py(공공기관·대학·병원)가
같은 검사를 쓴다. 복사해두면 한쪽만 고쳐져서 어긋난다 — 여기 한 곳만 고친다.

검사 기준은 2026-08-29 에 실제로 뚫린 것들에서 나왔다:
  잉크 0%       흰색 전용 로고. 카드에서 빈칸으로 보인다
  잉크 80% 초과  배경이 칠해진 배너(매드업의 검은 네비게이션 막대가 93%였다)
  경계상자 5% 미만  캔버스 구석의 점. 잉크 검사를 통과해버린다
                (애경산업은 og:image 1200x630 홍보 이미지가 잡혔다)
"""
import io
import re
import ssl
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def get(url, timeout=15, limit=400_000, _depth=0):
    """HTTP GET. **curl 로 한다** — 파이썬 요청이 막히는 서버가 있다.

    ⚠️ 2026-08-31 실측: 동해(dh.go.kr)·속초(sokcho.go.kr)·안양·용인·영동·
       강원고성 6곳이 curl 로는 전부 HTTP 200 인데 urllib 로는 전부 실패했다.
       같은 User-Agent 를 줘도 그렇다 — 헤더 순서·TLS 핑거프린트로 거르는
       것으로 보인다. CLAUDE.md 의 인스타그램 차단과 같은 부류다.
       그동안 이 서버들을 '접속 실패'로 처리하며 수집을 놓치고 있었다.
    """
    import subprocess, tempfile, os
    # ⚠️ content-type 을 stdout 에 섞으면 안 된다. PNG·SVG 같은 바이너리는
    #    끝부분이 잘릴 수 있다. 본문은 파일로 받고 헤더만 stdout 으로 받는다.
    fd, tmp = tempfile.mkstemp(prefix="vlc-")
    os.close(fd)
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), "-A", UA, "--compressed",
             "-o", tmp, "-w", "%{content_type}", url],
            capture_output=True)
        if r.returncode != 0:
            raise OSError(f"curl exit {r.returncode}: {url[:80]}")
        ctype = r.stdout.decode("ascii", "ignore").strip()
        with open(tmp, "rb") as f:
            body = f.read(limit)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if not body:
        raise OSError(f"빈 응답: {url[:80]}")

    # ⚠️ 지자체 사이트는 JS 리다이렉트로 시작하는 곳이 많다.
    #    동해시는 82바이트 짜리 <script>location.href="/www/index.do"</script>
    #    하나가 전부다. curl 은 이걸 못 따라가서 '빈 사이트'로 보였고,
    #    실측 114곳 중 37곳이 그렇게 실패로 처리되고 있었다.
    if _depth < 3 and len(body) < 6000:
        head = body[:2000].decode("utf-8", "ignore")
        # location.href 뿐 아니라 <meta http-equiv="refresh"> 도 쓴다.
        # 강동구·고양시가 그렇다 — 이걸 놓쳐서 97B·179B 껍데기만 받고 있었다.
        import urllib.parse as _up
        # ⚠️ location.href 가 여러 개일 수 있다. 시흥시는 첫 번째가 자기 자신
        #    ('https://www.siheung.go.kr')이고 두 번째가 진짜 목적지
        #    ('/newindex.jsp')다. 자기 URL 은 건너뛰어야 한다.
        cands = re.findall(
            r"""location(?:\.href|\.replace|)\s*(?:=|\()\s*["']([^"']+)""", head)
        cands += re.findall(
            r"""(?i)<meta[^>]+http-equiv=["']?refresh["']?[^>]+content=["'][^"']*?url=([^"'>\s]+)""",
            head)
        cur = url.rstrip("/")
        for c in cands:
            nxt = _up.urljoin(url, c)
            if nxt.rstrip("/") != cur:
                return get(nxt, timeout, limit, _depth + 1)
    return body, ctype


def get_text(url, timeout=15, limit=400_000):
    """HTML 을 **인코딩을 맞춰** 문자열로 돌려준다.

    ⚠️ 전부 UTF-8 로 디코딩하면 안 된다. 지자체 사이트에는 EUC-KR 이 남아 있다.
       서대문구는 121KB 본문인데 utf-8 로 읽으면 '서대문'이 **0회**,
       euc-kr 로 읽으면 143회다. 그래서 '사이트가 틀렸다'고 오판했다.
       실제로는 사이트도 정상이고 '로고 및 상징물' 페이지까지 있었다.
    """
    body, ctype = get(url, timeout, limit)
    enc = None
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    if m:
        enc = m.group(1)
    if not enc:
        m = re.search(rb'charset=["\']?([\w-]+)', body[:3000], re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
    for e in ([enc] if enc else []) + ["utf-8", "euc-kr", "cp949"]:
        try:
            t = body.decode(e, "strict")
            return t, ctype
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", "ignore"), ctype


def ink_ratio(data, is_svg):
    """(잉크비율, 크기, 내용경계상자비율). 실패하면 -1 을 돌려준다 — 0 과 구분된다."""
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
        # ⚠️ 문장 이미지 걸러내기.
        #    관악구에서 '홈페이지의 안전한 사용을 위해 자동 로그아웃 됩니다'
        #    안내 팝업 이미지를 로고로 가져왔다. 파일명에 logo 가 들어 있었다.
        #    글줄이 3덩이 이상으로 끊기면서 잉크가 옅으면 문장이다.
        #    로고도 2줄인 경우가 있어(강릉시) 줄 수만으로는 못 가른다.
        rows_with_ink = m.sum(axis=1) > 0
        runs, prev = 0, False
        for v in rows_with_ink:
            if v and not prev:
                runs += 1
            prev = bool(v)
        if runs >= 3 and m.mean() < 0.15:
            return -2.0, im.size, bbox      # -2 = 문장 이미지

        # ⚠️ 사진을 로고로 가져오는 사고. 2026-08-29 사용자 신고로 드러났다 —
        #    바디텍메드(의료 사진)·대현(인물)·KR모터스(오토바이)·OCI홀딩스(건물).
        #    사진은 색이 아주 많고 화면 대부분이 잉크다. 로고는 그렇지 않다.
        rgb = np.array(Image.open(io.BytesIO(data)).convert("RGB").resize((48, 48))) \
            if not is_svg else None
        if rgb is not None:
            colors = len({tuple(px) for px in rgb.reshape(-1, 3)[::3]})
            if colors > 500 and m.mean() > 0.70:
                return -3.0, im.size, bbox  # -3 = 사진

        return float(m.mean()), im.size, float(bbox)
    except Exception:
        return -1.0, (0, 0), -1.0


def pick_logo(page_html, base):
    """헤더 로고 후보를 우선순위로 고른다. SVG 가 원본이므로 앞에 둔다."""
    srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', page_html, re.I)
    srcs += re.findall(r'<source[^>]+srcset=["\']([^"\'\s]+)', page_html, re.I)
    named = [s for s in srcs if re.search(r"logo|ci[_\-.]|symbol|bi[_\-.]", s, re.I)]
    # ⚠️ SNS 아이콘 파일명에 'logo' 가 흔히 들어간다(sns_logo_facebook.png).
    #    기관 로고 자리에 유튜브·카카오톡 아이콘이 들어온 사례가 실제로 나왔다.
    #    남의 브랜드를 그 기관 로고로 등록하는 것이라 반드시 막는다.
    #    ⚠️ 느슨하게 짜면 멀쩡한 로고를 지운다 — 'img-bcu-logo.png' 의 bc,
    #       'sjlogo01.png' 의 sj 가 걸려 부천대·서정대가 빠질 뻔했다.
    #       플랫폼 이름은 앞뒤가 문자가 아닐 때만 본다.
    SNS = re.compile(
        r"(?<![a-z])(facebook|twitter|youtube|instagram|kakao|naver|linkedin|"
        r"tiktok|threads|pinterest|telegram|whatsapp|wechat|weibo|rss|sns|"
        r"blog|share)(?![a-z])", re.I)
    named = [s for s in named if not SNS.search(s)]

    def rank(s):
        w = 0 if s.lower().endswith(".svg") else 1
        # 흰색·역상 버전은 흰 배경에서 안 보인다 — 뒤로 민다
        if re.search(r"white|wh[_\-.]|invert|reverse|dark[_\-]bg|_w\.", s, re.I):
            w += 4
        return w

    return [urllib.parse.urljoin(base, s) for s in sorted(named, key=rank)][:4]


def _decode(body, ctype=""):
    """바이트를 인코딩을 맞춰 문자열로. get() 결과에 쓴다.

    ⚠️ utf-8 로 강제 디코딩하면 EUC-KR 사이트의 한글이 통째로 깨진다.
       서대문구는 그래서 '서대문'이 0회로 나와 '사이트가 틀렸다'고 오판했다.
    """
    enc = None
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    if m:
        enc = m.group(1)
    if not enc:
        m = re.search(rb'charset=["\']?([\w-]+)', body[:3000], re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
    for e in ([enc] if enc else []) + ["utf-8", "euc-kr", "cp949"]:
        try:
            return body.decode(e, "strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", "ignore")


def split_first_block(data):
    """이미지에 로고가 **여러 벌** 들어 있으면 첫 덩어리만 잘라 돌려준다.

    지자체 상징물 페이지는 컬러판·회색판을, 또는 국문·영문판을 한 이미지에
    나란히 담는 일이 잦다. 그대로 쓰면 카드에 로고가 두 개로 보인다.
      여주시   컬러 + 회색 그리드판
      목포시   국문·영문·한자 4개 조합
      청양군   로고 + 최소크기 규정
      군포시   제목 텍스트 + 브랜드 2벌
    세로 공백으로 제목 줄을 떼고, 가로 공백으로 첫 덩어리만 남긴다.

    ⚠️ 가운데 공백이 있다고 다 두 벌이 아니다. 심볼+글자 조합(영등포구·
       장흥군·함평군)이나 마스코트 여러 마리는 그대로 둬야 한다.
       실측한 공백 비율:
         정상  영등포구 8.3% · 장흥군 8.1% · 함평군 8.1% · 여주마스코트 10.1%
         두 벌  청양군 18.4% · 목포시 15.0% · 여주시 14.3%
       그래서 **12%** 를 경계로 둔다. 상주시(8.7%)처럼 못 잡는 것이 남지만,
       멀쩡한 로고를 쪼개는 것보다 덜 자르는 쪽이 낫다.

    돌려주는 값은 (바이트, 잘랐는지) 다. 못 자르면 원본 그대로.
    """
    try:
        import io
        import numpy as np
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        g = np.array(Image.alpha_composite(bg, im).convert("L"))
        ink = g < 235
        col, row = ink.sum(axis=0), ink.sum(axis=1)
        ci, ri = np.where(col > 0)[0], np.where(row > 0)[0]
        if len(ci) < 10 or len(ri) < 10:
            return data, False
        l, r, t, b = ci.min(), ci.max(), ri.min(), ri.max()

        # ★ 가로 줄 단위로 덩어리를 나누고 **잉크가 가장 많은 덩어리**를 고른다.
        #    원주시는 설명문 7줄 + 로고 1개가 한 이미지에 들어 있었는데
        #    (1200x847), 로고 덩어리의 잉크가 49,420 으로 압도적이었다.
        #    '위쪽 제목만 떼기'로는 중간에 낀 설명문을 못 걸러낸다.
        blocks, start = [], None
        for y in range(t, b + 2):
            v = row[y] if y < len(row) else 0
            if v > 0 and start is None:
                start = y
            elif v == 0 and start is not None:
                blocks.append((start, y, int(row[start:y].sum())))
                start = None
        if len(blocks) > 1:
            best = max(blocks, key=lambda x: x[2])
            # 최다 덩어리가 전체 잉크의 40% 를 넘을 때만 그것만 남긴다.
            # 고르게 퍼져 있으면 원래 한 덩이라는 뜻이다.
            if best[2] > sum(x[2] for x in blocks) * 0.4:
                t, b = best[0], best[1]
                col = ink[t:b].sum(axis=0)
                ci = np.where(col > 0)[0]
                if len(ci) < 10:
                    return data, False
                l, r = ci.min(), ci.max()

        # 가로: 폭의 6% 넘는 첫 공백에서 자른다
        w = r - l + 1
        cut, start = None, None
        for x in range(l, r + 1):
            if col[x] == 0 and start is None:
                start = x
            elif col[x] > 0 and start is not None:
                if x - start > w * 0.12:
                    cut = start
                    break
                start = None
        if cut is None:
            return data, False

        p = 6
        box = (max(0, l - p), max(0, t - p), min(im.width, cut + p), min(im.height, b + p))
        out = io.BytesIO()
        im.crop(box).save(out, "PNG", optimize=True)
        return out.getvalue(), True
    except Exception:
        return data, False
