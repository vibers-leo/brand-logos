#!/usr/bin/env python3
"""
티스토리 로고창고 자동 포스팅 스크립트

실행:
  python3 post.py                  # 전체 브랜드 순차 포스팅
  python3 post.py --brand samsung  # 특정 브랜드만
  python3 post.py --dry-run        # 실제 포스팅 없이 내용 미리보기
  python3 post.py --limit 5        # 최대 5개만
"""

import argparse, json, os, time, base64
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

BLOG_NAME = os.environ.get("TISTORY_BLOG", "logochango")
SITE_URL   = os.environ.get("SITE_URL", "https://로고창고.com")


def load_posted() -> set:
    if POSTED_FILE.exists():
        return set(json.loads(POSTED_FILE.read_text()))
    return set()

def save_posted(posted: set):
    POSTED_FILE.write_text(json.dumps(sorted(posted), ensure_ascii=False, indent=2))


def svg_to_data_uri(svg_path: Path) -> str:
    """SVG 파일을 data URI로 변환 (포스트에 직접 삽입)."""
    content = svg_path.read_bytes()
    b64 = base64.b64encode(content).decode()
    return f"data:image/svg+xml;base64,{b64}"


def build_post_content(brand: dict, logo_dir: Path) -> tuple[str, str]:
    """포스트 제목과 HTML 내용 반환."""
    name_ko = brand["name_ko"]
    name_en = brand.get("name_en", "")
    category = brand.get("category", "")
    domain   = brand.get("domain", "")

    title = f"{name_ko} 로고 SVG PNG 무료 다운로드 | 로고창고"

    # 로고 이미지 (SVG 우선, PNG 폴백)
    svg_path = logo_dir / "logo.svg"
    png_path = logo_dir / "logo.png"
    img_html = ""
    if svg_path.exists():
        uri = svg_to_data_uri(svg_path)
        img_html = f'<img src="{uri}" alt="{name_ko} 로고" style="max-width:300px; margin:20px auto; display:block;">'
    elif png_path.exists():
        b64 = base64.b64encode(png_path.read_bytes()).decode()
        uri = f"data:image/png;base64,{b64}"
        img_html = f'<img src="{uri}" alt="{name_ko} 로고" style="max-width:300px; margin:20px auto; display:block;">'

    content = f"""
<div style="text-align:center; padding:30px 0;">
{img_html}
</div>

<h2>{name_ko} 로고 소개</h2>
<p>
  <strong>{name_ko}</strong>{f' ({name_en})' if name_en else ''}의 공식 로고 파일을 SVG 형식으로 제공합니다.
  SVG(Scalable Vector Graphics)는 어떤 크기로 확대해도 깨지지 않는 벡터 형식으로,
  웹사이트 제작, 명함 디자인, 프레젠테이션 등 다양한 용도로 활용할 수 있습니다.
</p>

<h2>파일 정보</h2>
<table style="width:100%; border-collapse:collapse;">
  <tr style="background:#f5f5f5;">
    <th style="padding:10px; border:1px solid #ddd; text-align:left;">항목</th>
    <th style="padding:10px; border:1px solid #ddd; text-align:left;">내용</th>
  </tr>
  <tr>
    <td style="padding:10px; border:1px solid #ddd;">브랜드명</td>
    <td style="padding:10px; border:1px solid #ddd;">{name_ko}{f' / {name_en}' if name_en else ''}</td>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:10px; border:1px solid #ddd;">카테고리</td>
    <td style="padding:10px; border:1px solid #ddd;">{category}</td>
  </tr>
  <tr>
    <td style="padding:10px; border:1px solid #ddd;">파일 형식</td>
    <td style="padding:10px; border:1px solid #ddd;">SVG (벡터), PNG (래스터)</td>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:10px; border:1px solid #ddd;">라이선스</td>
    <td style="padding:10px; border:1px solid #ddd;">각 브랜드 공식 가이드라인 준수</td>
  </tr>
</table>

<h2>활용 예시</h2>
<ul>
  <li>웹사이트·앱 개발 시 파트너사 로고 표시</li>
  <li>회사 소개서·제안서 브랜드 섹션</li>
  <li>뉴스레터·마케팅 자료 제작</li>
  <li>개인 포트폴리오에서 협업 브랜드 표시</li>
</ul>

<div style="background:#f0f7ff; border-left:4px solid #3b82f6; padding:15px 20px; margin:30px 0; border-radius:4px;">
  <strong>🔍 더 많은 기업 로고가 필요하신가요?</strong><br>
  한국 대기업·스타트업·공공기관 로고를 한곳에서 — <a href="{SITE_URL}" target="_blank"><strong>로고창고</strong></a>에서 검색하고 바로 다운로드하세요.
  SVG·PNG 고품질 벡터 파일로 제공합니다.
</div>

<p style="color:#888; font-size:13px;">
  ※ 이 로고는 {name_ko}의 공식 로고이며, 상업적 사용 시 해당 브랜드의 사용 정책을 반드시 확인하세요.
  {f'공식 홈페이지: <a href="https://{domain}" target="_blank">{domain}</a>' if domain else ''}
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
