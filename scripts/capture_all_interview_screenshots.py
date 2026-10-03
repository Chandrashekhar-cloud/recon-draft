"""Capture high-resolution screenshots of all Recon Draft features for the comprehensive interview guide."""

from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def capture_all():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960}, device_scale_factor=2)
        page = context.new_page()

        # 1. Landing Page
        print("Capturing 1. Landing Page...")
        page.goto("http://127.0.0.1:5000/", wait_until="networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUTPUT_DIR / "1_landing_hero.png"), full_page=False)

        # 2. Run Workspace
        print("Capturing 2. Run Workspace...")
        page.goto("http://127.0.0.1:5000/run", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUTPUT_DIR / "2_run_workspace.png"), full_page=False)

        # 3. Review Workspace (Overview)
        print("Capturing 3. Review Workspace Overview...")
        page.goto("http://127.0.0.1:5000/review?run_id=full", wait_until="networkidle")
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUTPUT_DIR / "3_review_overview.png"), full_page=False)

        # 4. Tie-out Proof Card (Element screenshot)
        print("Capturing 4. Tie-out Proof Card...")
        tieout_card = page.locator("#tieout-card")
        if tieout_card.is_visible():
            tieout_card.screenshot(path=str(OUTPUT_DIR / "4_tieout_proof.png"))

        # 5. Human Review Candidates
        print("Capturing 5. Human Review Amber Banner & Candidates...")
        flagged_section = page.locator("#tab-review")
        if flagged_section.is_visible():
            flagged_section.screenshot(path=str(OUTPUT_DIR / "5_human_review_flagged.png"))

        # 6. Evals Page
        print("Capturing 6. Evals Benchmark Matrix...")
        page.goto("http://127.0.0.1:5000/evals", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUTPUT_DIR / "6_evals_matrix.png"), full_page=False)

        # 7. Under the Hood Page
        print("Capturing 7. Under the Hood Architecture & Trace...")
        page.goto("http://127.0.0.1:5000/hood", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUTPUT_DIR / "7_under_the_hood.png"), full_page=False)

        browser.close()
        print(f"\nAll screenshots captured successfully into {OUTPUT_DIR}")

if __name__ == "__main__":
    capture_all()
