from playwright.sync_api import sync_playwright
from pathlib import Path

SESSION = Path(__file__).parent / "session.json"
BLOG = "logochanggo"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(storage_state=str(SESSION), viewport={"width":1280,"height":900})
    page = ctx.new_page()

    print("관리 페이지 이동...")
    page.goto(f"https://{BLOG}.tistory.com/manage", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    page.screenshot(path=str(Path(__file__).parent / "manage.png"))
    print(f"현재 URL: {page.url}")

    links = page.evaluate("""() => {
        return [...document.querySelectorAll('a')].map(a => ({
            text: a.textContent.trim().slice(0,30),
            href: a.href.slice(0,100)
        })).filter(a => a.text.includes('글') || a.href.includes('post') || a.href.includes('write'))
    }""")
    print("=== 글쓰기 관련 링크 ===")
    for l in links[:10]: print(l)

    try:
        page.click("a[href*='write'], a:has-text('글쓰기')", timeout=5000)
        page.wait_for_timeout(3000)
        print(f"\n클릭 후 URL: {page.url}")
        page.screenshot(path=str(Path(__file__).parent / "editor.png"))
    except Exception as e:
        print(f"클릭 실패: {e}")

    inputs = page.evaluate("""() => {
        return [...document.querySelectorAll('input, textarea, [contenteditable="true"]')]
            .map(e => ({tag:e.tagName, id:e.id, name:e.name||'', ph:e.placeholder||'', cls:e.className.slice(0,60)}))
            .filter(e => e.id||e.name||e.ph)
    }""")
    print("\n=== 입력 요소 ===")
    for el in inputs: print(el)

    iframes = page.frames
    print(f"\n=== iframe {len(iframes)}개 ===")
    for f in iframes: print(f"  {f.url[:80]}")

    browser.close()
    print("\n완료 — manage.png, editor.png 확인")
