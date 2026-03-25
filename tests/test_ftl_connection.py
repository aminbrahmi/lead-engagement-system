# tests/test_ftl_connection.py
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page    = await browser.new_page()

        # Test 1 — page principale
        print("Test 1 : findthatlead.com")
        try:
            await page.goto("https://findthatlead.com",
                          wait_until="domcontentloaded", timeout=15000)
            print(f"  OK — {page.url}")
        except Exception as e:
            print(f"  FAIL — {e}")

        await asyncio.sleep(2)

        # Test 2 — app subdomain
        print("Test 2 : app.findthatlead.com")
        try:
            await page.goto("https://app.findthatlead.com",
                          wait_until="domcontentloaded", timeout=15000)
            print(f"  OK — {page.url}")
        except Exception as e:
            print(f"  FAIL — {e}")

        await asyncio.sleep(3)
        await page.screenshot(path="data/ftl_test.png")
        print("Screenshot saved → data/ftl_test.png")
        await browser.close()

asyncio.run(test()) 