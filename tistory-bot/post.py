#!/usr/bin/env python3
"""
티스토리 로고창고 자동 포스팅 스크립트

실행:
  python3 post.py                  # 전체 브랜드 순차 포스팅
  python3 post.py --brand samsung  # 특정 브랜드만
  python3 post.py --dry-run        # 실제 포스팅 없이 내용 미리보기
  python3 post.py --limit 5        # 최대 5개만
"""

import argparse, json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(__file__).parent.parent  # brand-logos/
SESSION_FILE = Path(__file__).parent / "session.json"
POSTED_FILE = Path(__file__).parent / "posted.json"   # 이미 올린 브랜드 기록
BRANDS_JSON = BASE / "_clients" / "brands.json"

# .env 로드
env_path = Path(__file__).parent / ".env"
for line in env_path.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

BLOG_NAME  = os.environ.get("TISTORY_BLOG", "logochanggo")
SITE_URL   = os.environ.get("SITE_URL", "https://logo.vibers.co.kr")
LOGO_CDN   = "https://logo.vibers.co.kr/_clients"  # GitHub Pages CDN (raw fallback: https://raw.githubusercontent.com/vibers-leo/brand-logos/main/_clients)


def load_posted() -> set:
    if POSTED_FILE.exists():
        return set(json.loads(POSTED_FILE.read_text()))
    return set()

def save_posted(posted: set):
    POSTED_FILE.write_text(json.dumps(sorted(posted), ensure_ascii=False, indent=2))


def build_post_content(brand: dict, logo_dir: Path) -> tuple[str, str]:
    """포스트 제목과 HTML 내용 반환."""
    brand_id = brand["id"]
    name_ko  = brand["name_ko"]
    name_en  = brand.get("name_en", "")
    category = brand.get("category", "")
    domain   = brand.get("domain", "")

    title = f"{name_ko} 로고 SVG·PNG 다운로드 | 로고창고"

    cdn = f"{LOGO_CDN}/{brand_id}"
    has_svg = (logo_dir / "logo.svg").exists()
    has_png = (logo_dir / "logo.png").exists()
    img_src = f"{cdn}/logo.png" if has_png else f"{cdn}/logo.svg"

    # 제공 파일 배지
    file_badges = ""
    if has_svg:
        file_badges += '<span style="display:inline-block;background:#e8f4fd;color:#1a73e8;border:1px solid #c2e0ff;border-radius:4px;padding:3px 10px;font-size:13px;font-weight:600;margin:3px;">SVG</span> '
    if has_png:
        file_badges += '<span style="display:inline-block;background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0;border-radius:4px;padding:3px 10px;font-size:13px;font-weight:600;margin:3px;">PNG</span>'

    name_display = f"{name_ko}" + (f" ({name_en})" if name_en else "")

    content = f"""
<!-- 로고 메인 미리보기 -->
<div style="display:flex; gap:16px; margin:24px 0; flex-wrap:wrap;">

  <div style="flex:1; min-width:200px; background:#ffffff; border:1px solid #e5e7eb; border-radius:12px; padding:32px; text-align:center;">
    <p style="font-size:11px; color:#9ca3af; margin:0 0 12px; text-transform:uppercase; letter-spacing:1px;">라이트 모드</p>
    <img src="{img_src}" alt="{name_ko} 로고" style="max-width:200px; max-height:100px; object-fit:contain;">
  </div>

  <div style="flex:1; min-width:200px; background:#111827; border:1px solid #374151; border-radius:12px; padding:32px; text-align:center;">
    <p style="font-size:11px; color:#6b7280; margin:0 0 12px; text-transform:uppercase; letter-spacing:1px;">다크 모드</p>
    <img src="{img_src}" alt="{name_ko} 로고" style="max-width:200px; max-height:100px; object-fit:contain; filter:brightness(0) invert(1);">
  </div>

</div>

<!-- 파일 정보 -->
<h2 style="font-size:18px; margin:32px 0 12px;">{name_display} 로고 파일 정보</h2>
<table style="width:100%; border-collapse:collapse; font-size:14px;">
  <tr style="background:#f9fafb;">
    <td style="padding:10px 14px; border:1px solid #e5e7eb; color:#6b7280; width:30%;">브랜드</td>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; font-weight:600;">{name_display}</td>
  </tr>
  <tr>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; color:#6b7280;">카테고리</td>
    <td style="padding:10px 14px; border:1px solid #e5e7eb;">{category}</td>
  </tr>
  <tr style="background:#f9fafb;">
    <td style="padding:10px 14px; border:1px solid #e5e7eb; color:#6b7280;">제공 형식</td>
    <td style="padding:10px 14px; border:1px solid #e5e7eb;">{file_badges}</td>
  </tr>
  {f'<tr><td style="padding:10px 14px; border:1px solid #e5e7eb; color:#6b7280;">공식 사이트</td><td style="padding:10px 14px; border:1px solid #e5e7eb;"><a href="https://{domain}" target="_blank" rel="nofollow">{domain}</a></td></tr>' if domain else ''}
</table>

<!-- SVG vs PNG 설명 -->
<h2 style="font-size:18px; margin:32px 0 12px;">SVG vs PNG, 어떤 파일을 쓸까요?</h2>
<table style="width:100%; border-collapse:collapse; font-size:14px;">
  <tr style="background:#f9fafb;">
    <th style="padding:10px 14px; border:1px solid #e5e7eb; text-align:left;">항목</th>
    <th style="padding:10px 14px; border:1px solid #e5e7eb; text-align:center;">SVG</th>
    <th style="padding:10px 14px; border:1px solid #e5e7eb; text-align:center;">PNG</th>
  </tr>
  <tr>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; color:#6b7280;">확대해도 선명</td>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; text-align:center;">✅</td>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; text-align:center;">❌ (픽셀 깨짐)</td>
  </tr>
  <tr style="background:#f9fafb;">
    <td style="padding:10px 14px; border:1px solid #e5e7eb; color:#6b7280;">웹 / 앱 개발</td>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; text-align:center;">✅ 권장</td>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; text-align:center;">가능</td>
  </tr>
  <tr>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; color:#6b7280;">MS 오피스 / 한컴</td>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; text-align:center;">제한적</td>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; text-align:center;">✅ 권장</td>
  </tr>
  <tr style="background:#f9fafb;">
    <td style="padding:10px 14px; border:1px solid #e5e7eb; color:#6b7280;">파일 크기</td>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; text-align:center;">작음</td>
    <td style="padding:10px 14px; border:1px solid #e5e7eb; text-align:center;">중간</td>
  </tr>
</table>

<!-- CTA -->
<div style="background:#f0f7ff; border:1px solid #bfdbfe; border-radius:12px; padding:20px 24px; margin:32px 0;">
  <p style="margin:0 0 8px; font-weight:700; font-size:16px;">더 많은 브랜드 로고가 필요하신가요?</p>
  <p style="margin:0 0 16px; color:#374151; font-size:14px;">
    한국 대기업·스타트업·공공기관 로고를 한 곳에서 모아볼 수 있어요.
    SVG·PNG 형식으로 바로 활용할 수 있도록 정리돼 있습니다.
  </p>
  <a href="{SITE_URL}" target="_blank"
     style="display:inline-block; background:#1a73e8; color:#fff; border-radius:8px; padding:10px 20px; font-weight:600; font-size:14px; text-decoration:none;">
    로고창고 방문하기 →
  </a>
</div>

<!-- 직접 URL 참조 -->
<h2 style="font-size:18px; margin:32px 0 12px;">개발자를 위한 직접 URL</h2>
<p style="font-size:14px; color:#374151;">
  아래 URL로 이미지를 바로 삽입하거나 다운로드할 수 있습니다.
  (logo.vibers.co.kr에서 서비스됩니다)
</p>
<pre style="background:#1f2937; color:#e5e7eb; border-radius:8px; padding:16px; font-size:13px; overflow-x:auto;">{cdn}/logo.svg
{cdn}/logo.png</pre>

<p style="color:#9ca3af; font-size:12px; margin-top:32px;">
  이 로고는 각 브랜드의 소유이며, 공식 사용 목적 외 상업적 이용 시 해당 브랜드의 브랜드 가이드라인을 반드시 확인하세요.
  본 컬렉션은 디자이너·개발자의 레퍼런스 목적으로 수집·정리된 파일입니다.
</p>
"""
    return title, content


def post_to_tistory(page, title: str, content: str, tags: list[str], dry_run: bool) -> bool:
    """티스토리에 글을 발행한다. 성공하면 True."""
    if dry_run:
        print(f"\n[DRY RUN] 제목: {title}")
        print(f"[DRY RUN] 태그: {', '.join(tags)}")
        print(f"[DRY RUN] 내용 길이: {len(content)}자")
        return True

    try:
        # 글쓰기 페이지 (관리 홈 → 글쓰기 클릭 방식)
        page.goto(f"https://{BLOG_NAME}.tistory.com/manage", wait_until="networkidle", timeout=30000)
        time.sleep(1)
        page.click("a[href*='newpost'], a[href*='/manage/post']:has-text('글쓰기')", timeout=5000)
        page.wait_for_url("**/newpost/**", timeout=15000)
        time.sleep(2)

        # 제목 입력
        page.fill("#post-title-inp", title)
        time.sleep(0.5)

        # 본문: aria-hidden 처리된 textarea에 JS로 직접 값 주입
        page.evaluate(f"""
            (html) => {{
                const ta = document.querySelector('#editor-tistory');
                if (ta) {{
                    // 네이티브 setter로 React/Vue 상태 업데이트까지 트리거
                    const nativeSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value').set;
                    nativeSetter.call(ta, html);
                    ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            }}
        """, content)
        time.sleep(1)

        # 태그 입력
        try:
            for tag in tags[:10]:  # 최대 10개
                page.fill("#tagText", tag)
                page.keyboard.press("Enter")
                time.sleep(0.2)
        except:
            pass

        # 완료 버튼 클릭 → 발행 레이어 열림
        page.click("#publish-layer-btn", timeout=5000)
        time.sleep(1)

        # 공개 라디오 버튼 선택 (기본값이 비공개이므로 반드시 필요)
        page.click("#open20", timeout=3000)
        time.sleep(0.5)

        # 발행 버튼 클릭
        page.click("#publish-btn", timeout=3000)

        time.sleep(2)
        print(f"  ✅ 발행 완료: {title[:40]}")
        return True

    except Exception as e:
        print(f"  ❌ 실패: {e}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand",   help="특정 브랜드 ID만 포스팅")
    parser.add_argument("--dry-run", action="store_true", help="실제 포스팅 없이 미리보기")
    parser.add_argument("--limit",   type=int, default=999, help="최대 포스팅 개수")
    parser.add_argument("--delay",   type=int, default=60, help="포스트 간 대기 시간(초)")
    args = parser.parse_args()

    if not SESSION_FILE.exists() and not args.dry_run:
        print("❌ session.json 없음. 먼저 login.py를 실행하세요.")
        return

    # 브랜드 목록 로드
    db = json.loads(BRANDS_JSON.read_text())
    brands = db["brands"]
    if args.brand:
        brands = [b for b in brands if b["id"] == args.brand]
        if not brands:
            print(f"❌ 브랜드 '{args.brand}' 없음")
            return

    posted = load_posted()
    todo = [b for b in brands if b["id"] not in posted][:args.limit]

    print(f"포스팅 예정: {len(todo)}개 (이미 완료: {len(posted)}개)")
    if not todo:
        print("모두 완료됐습니다.")
        return

    with sync_playwright() as p:
        if args.dry_run:
            browser = page = None
        else:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                storage_state=str(SESSION_FILE),
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

        for i, brand in enumerate(todo):
            brand_id = brand["id"]
            logo_dir = BASE / "_clients" / brand_id
            print(f"\n[{i+1}/{len(todo)}] {brand['name_ko']} ({brand_id})")

            title, content = build_post_content(brand, logo_dir)
            tags = [brand["name_ko"], brand.get("name_en", ""), "로고", "SVG", "무료다운로드", brand.get("category", "")]
            tags = [t for t in tags if t]

            success = post_to_tistory(page, title, content, tags, args.dry_run)

            if success and not args.dry_run:
                posted.add(brand_id)
                save_posted(posted)

            if i < len(todo) - 1 and not args.dry_run:
                print(f"  ⏳ {args.delay}초 대기...")
                time.sleep(args.delay)

        if browser:
            browser.close()

    print(f"\n완료: {len(posted)}개 포스팅됨")


if __name__ == "__main__":
    main()
