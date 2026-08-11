#!/usr/bin/env python3
"""
recollect-logos.py — 플레이스홀더 로고 재수집
Clearbit → Google Favicon 순으로 시도
Usage: python3 scripts/recollect-logos.py
"""

# 저장 가드 — 확장자와 내용이 다르면 쓰지 않는다 (404 HTML 이 logo.svg 로
# 저장되던 사고 재발 방지).
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent / "scripts"))
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from assetguard import safe_write


import ssl
import time
import urllib.request
from pathlib import Path

CLIENTS = Path(__file__).parent.parent / "_clients"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

BRANDS = [
    ("baemin", "baemin.com"), ("ably", "ably.kr"), ("zigzag", "zigzag.kr"),
    ("brandi-co", "brandi.co.kr"), ("kbank-co", "kbank.co.kr"),
    ("kakaomobility", "kakaomobility.com"), ("naverwebtoon", "naverwebtoon.com"),
    ("seezn", "seezn.com"), ("ocn-co", "ocn.co.kr"), ("hani-co", "hani.co.kr"),
    ("etnews", "etnews.com"), ("renaultkorea", "renaultkorea.com"),
    ("orion-co", "orion.co.kr"), ("binggrae-co", "binggrae.co.kr"),
    ("parisbaguette-co", "parisbaguette.co.kr"), ("coffeebean-co", "coffeebean.co.kr"),
    ("goobne", "goobne.com"), ("clio-co", "clio.co.kr"), ("peripera-co", "peripera.co.kr"),
    ("yuhan-co", "yuhan.co.kr"), ("kyoborealco", "kyoborealco.com"),
    ("sh-or", "sh.or.kr"), ("srail", "srail.kr"), ("dabang", "dabang.com"),
    ("petfriends-co", "petfriends.co.kr"), ("kyobobook-co", "kyobobook.co.kr"),
    ("class101", "class101.net"), ("nid-naver", "nid.naver.com"),
    ("severance-or", "severance.or.kr"), ("kbia-or", "kbia.or.kr"),
    ("kba-or", "kba.or.kr"), ("smartstore-naver", "smartstore.naver.com"),
    ("dlive-co", "dlive.co.kr"), ("hema", "hema.com"), ("7-eleven-co", "7-eleven.co.kr"),
    ("ministop-co", "ministop.co.kr"), ("kticloud", "kticloud.com"),
    ("ncloudplatform", "ncloudplatform.com"), ("bbo-co", "bbo.co.kr"),
    ("gimbap", "gimbap.net"), ("northfacekorea", "northfacekorea.com"),
    ("abercrombie-co", "abercrombie.co.kr"), ("sjyc-co", "sjyc.co.kr"),
    ("chong-kun-dang", "chong-kun-dang.com"), ("koreacrescentresearch", "koreacrescentresearch.com"),
    ("sk-biopharma", "sk-biopharma.com"), ("sk-bioscience-co", "sk-bioscience.co.kr"),
    ("posco-e", "posco-e.com"), ("daewooconstruction", "daewooconstruction.com"),
    ("seoahn", "seoahn.com"), ("skenergyplus-co", "skenergyplus.co.kr"),
    ("kumhopchem", "kumhopchem.com"), ("shillahotel", "shillahotel.com"),
    ("petproduct-co", "petproduct.co.kr"), ("kraftonclub", "kraftonclub.com"),
    ("naverpay", "naverpay.me"), ("anytime", "anytime.kr"), ("mcdfit-co", "mcdfit.co.kr"),
    ("bodyprofile-co", "bodyprofile.co.kr"), ("medilive-co", "medilive.co.kr"),
    ("sktadmission-co", "sktadmission.co.kr"), ("bespin", "bespin.global"),
    ("cosco-co", "cosco.co.kr"), ("nhn", "nhn.com"), ("bugs-co", "bugs.co.kr"),
    ("vibe-naver", "vibe.naver.com"), ("viva-republica", "viva-republica.com"),
    ("nicepay-co", "nicepay.co.kr"), ("kcb-co", "kcb.co.kr"),
    ("naverfinancial", "naverfinancial.com"), ("okfinancialgroup", "okfinancialgroup.com"),
    ("kyobolife-co", "kyobolife.co.kr"), ("dear-klairs", "dear-klairs.com"),
    ("rovectin", "rovectin.com"), ("dr-jart", "dr.jart.com"), ("goodal-co", "goodal.co.kr"),
    ("skinfood", "skinfood.com"), ("whoo", "whoo.com"), ("kuho", "kuho.com"),
    ("87mm", "87mm.kr"), ("ader-error", "ader-error.com"), ("namyang-co", "namyang.co.kr"),
    ("crownconfectionery", "crownconfectionery.com"), ("paldo-co", "paldo.co.kr"),
    ("yungjin", "yungjin.com"), ("kwangdong-co", "kwangdong.co.kr"),
    ("sisa-co", "sisa.co.kr"), ("yanadoo", "yanadoo.com"), ("woowa", "woowa.net"),
    ("skresorts", "skresorts.com"), ("otis-co", "otis.co.kr"), ("kimm-re", "kimm.re.kr"),
    ("kocca-or", "kocca.or.kr"), ("mlit-go", "mlit.go.kr"), ("dyson-co", "dyson.co.kr"),
]


def get(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for verify in (True, False):
        try:
            ctx = ssl.create_default_context()
            if not verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
                ct = r.headers.get_content_type() or ""
                return r.read(), ct
        except ssl.SSLError:
            if not verify:
                return b"", ""
        except Exception:
            return b"", ""
    return b"", ""


def is_img(ct: str, data: bytes, min_bytes: int) -> bool:
    return ct.startswith("image/") and "html" not in ct and len(data) >= min_bytes


def save(brand_id: str, data: bytes):
    p = CLIENTS / brand_id / "logo.png"
    return safe_write(p, data)


def main():
    ok_cb, ok_fav, fail = [], [], []
    total = len(BRANDS)

    for i, (bid, domain) in enumerate(BRANDS, 1):
        tag = f"[{i:3d}/{total}] {bid:<30s}"

        data, ct = get(f"https://logo.clearbit.com/{domain}?size=800")
        if is_img(ct, data, 10_000):
            save(bid, data)
            print(f"{tag} ✅ Clearbit  {len(data)//1024}KB")
            ok_cb.append(bid)
            time.sleep(0.4)
            continue

        data, ct = get(f"https://www.google.com/s2/favicons?domain={domain}&sz=256")
        if is_img(ct, data, 3_000):
            save(bid, data)
            print(f"{tag} ✅ Favicon   {len(data)//1024}KB")
            ok_fav.append(bid)
            time.sleep(0.4)
            continue

        print(f"{tag} ❌ 실패")
        fail.append((bid, domain))
        time.sleep(0.4)

    print(f"\n✅ Clearbit: {len(ok_cb)}  ✅ Favicon: {len(ok_fav)}  ❌ 실패: {len(fail)}")
    if fail:
        print("\n[실패 목록]")
        for bid, dom in fail:
            print(f"  {bid}  {dom}")


if __name__ == "__main__":
    main()
