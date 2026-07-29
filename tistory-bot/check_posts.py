from playwright.sync_api import sync_playwright
import time
from pathlib import Path

SESSION_FILE = Path(__file__).parent / "session.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(storage_state=str(SESSION_FILE))
    page = context.new_page()
    
    page.goto("https://logochanggo.tistory.com/manage/posts/", wait_until="networkidle")
    time.sleep(3)
    
    # 전체 HTML 저장
    html = page.content()
    with open("/tmp/posts_page.html", "w") as f:
        f.write(html)
    print("HTML 저장됨: /tmp/posts_page.html")
    print("페이지 URL:", page.url)
    
    time.sleep(3)
    browser.close()
