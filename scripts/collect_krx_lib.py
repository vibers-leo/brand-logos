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


def get(url, timeout=15, limit=400_000):
    r = urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout, context=CTX)
    return r.read(limit), r.headers.get("Content-Type", "")


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
