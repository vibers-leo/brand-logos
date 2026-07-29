#!/usr/bin/env python3
"""
1단계: 수동으로 티스토리 카카오 로그인 후 세션 저장
딱 한 번만 실행하면 됩니다.

실행: python3 login.py
"""

from playwright.sync_api import sync_playwright
import os, json
from pathlib import Path

SESSION_FILE = Path(__file__).parent / "session.json"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 브라우저 보이게
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("티스토리 로그인 페이지 열기...")
        page.goto("https://www.tistory.com/auth/login")
        page.wait_for_load_state("networkidle")

        print("\n브라우저에서 카카오 계정으로 직접 로그인해주세요.")
        print("로그인 완료 후 티스토리 메인 화면이 나오면 Enter를 눌러주세요.")
        input(">>> ")

        # 로그인 확인
        if "tistory.com" in page.url:
            context.storage_state(path=str(SESSION_FILE))
            print(f"\n✅ 세션 저장 완료: {SESSION_FILE}")
            print("이제 post.py를 실행해도 됩니다.")
        else:
            print("❌ 로그인이 완료되지 않은 것 같습니다. 다시 시도해주세요.")

        browser.close()

if __name__ == "__main__":
    main()
