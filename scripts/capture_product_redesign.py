"""Browser screenshot & interactive validation script for Recon Draft product redesign."""

from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACTS_DIR = Path(r"C:\Users\chand\.gemini\antigravity-ide\brain\2afb1203-f8fa-4138-a4eb-7a98245b3593")

def capture_all():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1360, "height": 850})
        page = context.new_page()

        # 1. Landing Page (Light Mode)
        print("1. Capturing Landing Page (Light)...")
        page.goto("http://127.0.0.1:5000/", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.screenshot(path=str(ARTIFACTS_DIR / "product_landing_light.png"), full_page=True)

        # 2. Click CTA "Open Reconciliation" to navigate to /run
        print("2. Clicking 'Open Reconciliation'...")
        page.click("#hero-open-btn")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=str(ARTIFACTS_DIR / "product_run_light.png"), full_page=True)

        # 3. Review Page (Full Case)
        print("3. Capturing Review Page (Full Case)...")
        page.goto("http://127.0.0.1:5000/review/full", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(ARTIFACTS_DIR / "product_review_light.png"), full_page=True)

        # 4. Open Exception Detail Modal
        print("4. Testing Exception Detail Modal...")
        page.click("#tab-btn-reconciling")
        page.wait_for_timeout(400)
        # Click the first 'Review' button in the reconciling table
        review_btn = page.locator("#reconciling-table-body button:has-text('Review')").first
        if review_btn.is_visible():
            review_btn.click()
            page.wait_for_timeout(400)
            page.screenshot(path=str(ARTIFACTS_DIR / "product_exception_modal.png"))
            # Close modal
            page.click(".modal-close-btn")
            page.wait_for_timeout(300)

        # 5. Check Matched Tab & Tie-out
        print("5. Checking Matched tab and Memo tab...")
        page.click("#tab-btn-matched")
        page.wait_for_timeout(400)
        page.screenshot(path=str(ARTIFACTS_DIR / "product_review_matched.png"))

        page.click("#tab-btn-memo")
        page.wait_for_timeout(400)
        page.screenshot(path=str(ARTIFACTS_DIR / "product_review_memo.png"))

        # 6. Evaluations Page
        print("6. Capturing Evaluations Page...")
        page.goto("http://127.0.0.1:5000/evals", wait_until="networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=str(ARTIFACTS_DIR / "product_evals_light.png"), full_page=True)

        # 7. System Architecture Page (/hood)
        print("7. Capturing System Architecture (/hood)...")
        page.goto("http://127.0.0.1:5000/hood", wait_until="networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=str(ARTIFACTS_DIR / "product_system_light.png"), full_page=True)

        # 8. Dark Mode Validation
        print("8. Capturing Dark Mode across pages...")
        page.click("#theme-toggle-btn")
        page.wait_for_timeout(400)
        page.screenshot(path=str(ARTIFACTS_DIR / "product_system_dark.png"), full_page=True)

        page.goto("http://127.0.0.1:5000/review/full", wait_until="networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=str(ARTIFACTS_DIR / "product_review_dark.png"), full_page=True)

        page.goto("http://127.0.0.1:5000/", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.screenshot(path=str(ARTIFACTS_DIR / "product_landing_dark.png"), full_page=True)

        browser.close()
        print("All product screenshots successfully captured!")

if __name__ == "__main__":
    capture_all()
