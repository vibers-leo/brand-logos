from playwright.sync_api import sync_playwright
import json
from pathlib import Path

SESSION_FILE = Path(__file__).parent / "session.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(storage_state=str(SESSION_FILE))
    page = context.new_page()
    
    # 임시저장 목록 확인
    page.goto("https://logochanggo.tistory.com/manage/posts/", wait_until="networkidle")
    import time; time.sleep(2)
    
    # 페이지 소스에서 글 목록 확인
    posts = page.evaluate("""() => {
        const rows = document.querySelectorAll('.list_post tr, .post-item, [data-post-id]');
        return Array.from(rows).slice(0, 20).map(r => r.textContent?.trim().substring(0, 100));
    }""")
    print("포스트 목록:")
    for p in posts:
        if p: print(" -", p)
    
    time.sleep(5)
    browser.close()
