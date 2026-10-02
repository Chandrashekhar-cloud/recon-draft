import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\chand\.gemini\antigravity-ide\brain\2afb1203-f8fa-4138-a4eb-7a98245b3593"

def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        print("Navigating to http://127.0.0.1:5000/evals...")
        page.goto("http://127.0.0.1:5000/evals", wait_until="networkidle")

        # Wait for dynamic fetch of /api/evals/summary
        page.wait_for_selector("#card-v0-pass-rate")
        time.sleep(1)

        # 1. Headline Row Cards Verification
        v0_pass = page.locator("#card-v0-pass-rate").inner_text().strip()
        v0_false_matches = page.locator("#card-v0-false-matches").inner_text().strip()
        v0_cost = page.locator("#card-v0-avg-cost").inner_text().strip()

        v1_pass = page.locator("#card-v1-pass-rate").inner_text().strip()
        v1_false_matches = page.locator("#card-v1-false-matches").inner_text().strip()

        v2_pass = page.locator("#card-v2-pass-rate").inner_text().strip()
        v2_false_matches = page.locator("#card-v2-false-matches").inner_text().strip()
        v2_cost = page.locator("#card-v2-avg-cost").inner_text().strip()

        print(f"v0: pass={v0_pass}, false_matches={v0_false_matches}, cost={v0_cost}")
        print(f"v1: pass={v1_pass}, false_matches={v1_false_matches}")
        print(f"v2: pass={v2_pass}, false_matches={v2_false_matches}, cost={v2_cost}")

        assert "50" in v0_pass, f"Unexpected v0 pass rate: {v0_pass}"
        assert v0_false_matches == "2", f"Unexpected v0 false matches: {v0_false_matches}"
        assert "100" in v1_pass, f"Unexpected v1 pass rate: {v1_pass}"
        assert v1_false_matches == "0", f"Unexpected v1 false matches: {v1_false_matches}"
        assert "100" in v2_pass, f"Unexpected v2 pass rate: {v2_pass}"
        assert v2_false_matches == "0", f"Unexpected v2 false matches: {v2_false_matches}"

        # 2. SVG Bar Charts Verification
        pass_svg = page.locator("#svg-chart-pass-rate")
        fm_svg = page.locator("#svg-chart-false-matches")
        assert pass_svg.count() == 1
        assert fm_svg.count() == 1
        assert "v0" in pass_svg.inner_html()
        assert "v2" in pass_svg.inner_html()
        assert "v0" in fm_svg.inner_html()
        print("SVG Charts verified.")

        # 3. Big Comparison Table Verification
        rows = page.locator("#eval-matrix-tbody tr")
        print(f"Total rows in matrix: {rows.count()}")
        assert rows.count() >= 10, f"Expected at least 10 scenario rows, got {rows.count()}"

        # 4. What the evals caught & Golden set cards
        caught_card = page.locator("#caught-card")
        golden_card = page.locator("#golden-set-card")
        assert caught_card.count() == 1
        assert golden_card.count() == 1
        assert "Force-matched ambiguous" in caught_card.inner_text()
        assert "True World Simulation" in golden_card.inner_text()
        assert "Plant Controlled Accounting Traps" in golden_card.inner_text()
        print("Insight cards verified.")

        # 5. Footer verification
        footer = page.locator("#evals-tiny-footer")
        assert "Scored by deterministic Python. No AI is used to grade." in footer.inner_text()
        print("Footer text verified.")

        # Take full overview screenshot
        overview_path = os.path.join(ARTIFACT_DIR, "evals_page_overview.png")
        page.screenshot(path=overview_path, full_page=True)
        print(f"Saved overview screenshot to {overview_path}")

        # 6. Test Cell Click Modal (Expected vs Actual Diff)
        # Click the v0 cell for 'tricky' or 'errors' (which is a FAIL in v0)
        # Find the fail cell button in v0
        fail_btn = page.locator(".eval-cell-fail").first
        print("Clicking fail button to open modal...")
        fail_btn.click()
        time.sleep(1)

        modal = page.locator("#eval-detail-modal")
        assert "open" in modal.get_attribute("class")
        modal_title = page.locator("#modal-title").inner_text()
        print(f"Modal opened: {modal_title}")

        # Wait for detail API fetch
        page.wait_for_selector("#modal-failures-section", state="visible")
        failures_text = page.locator("#modal-failures-section").inner_text()
        print(f"Failures in modal: {failures_text[:120]}...")

        # Take modal screenshot
        modal_path = os.path.join(ARTIFACT_DIR, "evals_cell_modal_diff.png")
        page.screenshot(path=modal_path)
        print(f"Saved modal diff screenshot to {modal_path}")

        # Close modal
        close_btn = page.locator("#eval-detail-modal .modal-header button")
        close_btn.click()
        time.sleep(0.5)

        # 7. Test "Run all evals" button triggers background progress
        print("Testing 'Run All Evals' background runner trigger...")
        run_btn = page.locator("#btn-run-all-evals")
        run_btn.click()
        time.sleep(0.8)

        # Check progress card is visible
        prog_card = page.locator("#evals-progress-card")
        assert prog_card.is_visible(), "Progress card should be visible after clicking Run All Evals"
        prog_pct = page.locator("#evals-progress-pct").inner_text()
        print(f"Eval progress started: {prog_pct}")

        # Take progress running screenshot
        progress_path = os.path.join(ARTIFACT_DIR, "evals_progress_running.png")
        page.screenshot(path=progress_path)
        print(f"Saved progress screenshot to {progress_path}")

        # Wait for eval completion
        print("Waiting for background evals to finish...")
        for _ in range(30):
            time.sleep(0.5)
            if not prog_card.is_visible() or run_btn.is_enabled():
                print("Evals runner completed!")
                break

        time.sleep(1)
        # Verify toast or updated last-run pill
        last_run_text = page.locator("#eval-last-run-pill").inner_text()
        print(f"Last Run Pill after re-run: {last_run_text}")

        # Final full page screenshot after run
        final_path = os.path.join(ARTIFACT_DIR, "evals_page_completed.png")
        page.screenshot(path=final_path, full_page=True)
        print(f"Saved final screenshot to {final_path}")

        browser.close()
        print("All Evals page assertions and visual checks PASSED successfully!")

if __name__ == "__main__":
    verify()
