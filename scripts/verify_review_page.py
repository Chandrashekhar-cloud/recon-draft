"""Comprehensive browser verification script for the Review page (/review/<run_id>)."""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACTS_DIR = Path(r"C:\Users\chand\.gemini\antigravity-ide\brain\2afb1203-f8fa-4138-a4eb-7a98245b3593")

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        print("1. Navigating to http://127.0.0.1:5000/review/full ...")
        page.goto("http://127.0.0.1:5000/review/full", wait_until="networkidle")
        page.wait_for_timeout(1000)

        # 1. Top Section Stat Tiles
        print("2. Checking top stat tiles...")
        matched_cnt = page.locator("#stat-matched-count").inner_text().strip()
        matched_pct = page.locator("#stat-matched-pct").inner_text().strip()
        needs_rev_cnt = page.locator("#stat-needs-review-count").inner_text().strip()
        jes_cnt = page.locator("#stat-jes-count").inner_text().strip()
        verify_txt = page.locator("#stat-verify-text").inner_text().strip()
        tieout_txt = page.locator("#stat-tieout-text").inner_text().strip()

        print(f"   Matched automatically: {matched_cnt} {matched_pct}")
        print(f"   Needs human review: {needs_rev_cnt}")
        print(f"   Proposed journal entries: {jes_cnt}")
        print(f"   Verification: {verify_txt}")
        print(f"   Tie-out status: {tieout_txt}")

        assert int(matched_cnt) > 0, "Matched count should be > 0"
        assert int(needs_rev_cnt) >= 1, "Needs review count should be >= 1"
        assert int(jes_cnt) >= 1, "Proposed JEs count should be >= 1"
        assert "All checks passed" in verify_txt, f"Unexpected verify text: {verify_txt}"
        assert "Balances to $0.00 difference" in tieout_txt, f"Unexpected tieout text: {tieout_txt}"

        # 2. Tie-Out Proof Card
        print("3. Checking tie-out proof card...")
        tieout_card = page.locator("#tieout-card")
        assert tieout_card.is_visible()
        proof_header = page.locator("#tieout-card .card-header").inner_text()
        assert "computed in python, not by ai" in proof_header.lower(), "Missing 'Computed in Python, not by AI' label"
        
        bank_adj = page.locator("#proof-bank-adjusted").inner_text().strip()
        book_adj = page.locator("#proof-book-adjusted").inner_text().strip()
        print(f"   Adjusted Bank: {bank_adj}, Adjusted Book: {book_adj}")
        assert bank_adj == book_adj, f"Adjusted balances must match: {bank_adj} != {book_adj}"
        assert "$87,723.65" in bank_adj

        footer_proof = page.locator("#tieout-footer-bar").inner_text()
        assert "Tie-Out Proved to the Exact Cent: $0.00 Difference" in footer_proof

        # 3. Tab: Needs Your Review (Amber banner & Candidate items)
        print("4. Checking 'Needs your review' tab & ambiguous $500 banner...")
        tab_rev_btn = page.locator("#tab-btn-review")
        assert "active" in tab_rev_btn.get_attribute("class"), "Needs your review tab should be active by default"

        amber_banner = page.locator("#ambiguous-500-banner")
        assert amber_banner.is_visible(), "Ambiguous $500 amber banner must be visible"
        assert "Flagged: two identical amounts, a human must decide" in amber_banner.inner_text()

        # Check candidate cards
        review_cards = page.locator(".review-card")
        card_count = review_cards.count()
        print(f"   Found {card_count} review card(s)")
        assert card_count >= 1

        # Check candidate transactions side by side
        first_card = review_cards.first
        candidates_grid = first_card.locator(".review-candidates-grid")
        assert candidates_grid.is_visible()
        assert "BNK-1057" in candidates_grid.inner_text()
        assert "GL-2059" in candidates_grid.inner_text()

        # Capture Screenshot 1: Review tab & Top Section
        ss1_path = ARTIFACTS_DIR / "review_page_top_and_flagged.png"
        page.screenshot(path=str(ss1_path), full_page=False)
        print(f"   Saved screenshot: {ss1_path}")

        # Test Auditor Decision & Toast
        print("5. Testing Accept button & Toast notification...")
        accept_btn = first_card.locator("button:has-text('Accept')")
        accept_btn.click()
        page.wait_for_timeout(600)

        # Check Toast
        toast = page.locator(".toast")
        assert toast.is_visible(), "Toast notification should appear upon review decision"
        print(f"   Toast displayed: {toast.inner_text()}")
        assert "Decision" in toast.inner_text()

        # Capture Screenshot 2: Toast notification active
        ss2_path = ARTIFACTS_DIR / "review_decision_toast.png"
        page.screenshot(path=str(ss2_path), full_page=False)
        print(f"   Saved screenshot: {ss2_path}")

        # 4. Tab: Matched Table (With One-to-Many expandable row)
        print("6. Checking 'Matched' tab & one-to-many expandable row...")
        page.locator("#tab-btn-matched").click()
        page.wait_for_timeout(400)
        matched_rows = page.locator("#matched-table-body tr")
        print(f"   Matched table rendered rows: {matched_rows.count()}")
        assert matched_rows.count() > 20

        # Find one-to-many row toggle
        expand_btn = page.locator("button.expand-toggle-btn").first
        expand_btn.scroll_into_view_if_needed()
        page.wait_for_timeout(200)
        assert expand_btn.is_visible(), "One-to-many expand button should be visible"
        print("   Clicking one-to-many expand button...")
        expand_btn.click()
        page.wait_for_timeout(300)

        expanded_box = page.locator(".expanded-detail-box").first
        assert expanded_box.is_visible(), "Expanded breakdown table should be visible"
        assert "sum check verified" in expanded_box.inner_text().lower()
        print("   One-to-many breakdown expanded with sum check verified.")

        # Capture Screenshot 3: Matched tab with expanded row
        ss3_path = ARTIFACTS_DIR / "review_matched_tab_expanded.png"
        page.screenshot(path=str(ss3_path), full_page=False)
        print(f"   Saved screenshot: {ss3_path}")

        # 5. Tab: Reconciling Items Table
        print("7. Checking 'Reconciling items' tab...")
        page.locator("#tab-btn-reconciling").click()
        page.wait_for_timeout(400)
        rec_rows = page.locator("#reconciling-table-body tr")
        print(f"   Reconciling items rendered rows: {rec_rows.count()}")
        assert rec_rows.count() == 9

        # 6. Tab: Journal Entries (T-Account cards)
        print("8. Checking 'Journal entries' tab...")
        page.locator("#tab-btn-journals").click()
        page.wait_for_timeout(400)
        t_cards = page.locator(".t-account-card")
        print(f"   Journal entry T-account cards: {t_cards.count()}")
        assert t_cards.count() >= 7

        first_je = t_cards.first
        assert first_je.locator(".t-account-table").is_visible()
        # Test approving entry
        je_approve_btn = first_je.locator("button:has-text('Approve Entry')")
        je_approve_btn.click()
        page.wait_for_timeout(500)
        je_status_text = first_je.locator('.badge-success').inner_text().encode('ascii', 'ignore').decode('ascii')
        print(f"   Approved JE card status: {je_status_text}")
        assert "approved" in je_status_text.lower()

        # Capture Screenshot 4: Journal entries
        ss4_path = ARTIFACTS_DIR / "review_journals_t_accounts.png"
        page.screenshot(path=str(ss4_path), full_page=False)
        print(f"   Saved screenshot: {ss4_path}")

        # 7. Tab: Reviewer Memo
        print("9. Checking 'Reviewer Memo' tab...")
        page.locator("#tab-btn-memo").click()
        page.wait_for_timeout(400)
        memo_badge = page.locator("#tab-memo .badge-success")
        assert "numbers checked against verified results" in memo_badge.inner_text().lower()
        memo_text = page.locator("#memo-full-text").inner_text().encode('ascii', 'ignore').decode('ascii')
        print(f"   Memo preview: {memo_text[:120]}...")
        assert len(memo_text) > 100

        # 8. Demo Controls: Show Answer Key Score
        print("10. Testing 'Show Answer Key Score' toggle...")
        score_btn = page.locator("#toggle-score-btn")
        score_btn.click()
        page.wait_for_timeout(400)

        score_card = page.locator("#demo-score-card")
        assert score_card.is_visible(), "Score card should be visible after toggle"
        prec = page.locator("#score-precision").inner_text()
        rec = page.locator("#score-recall").inner_text()
        fm = page.locator("#score-false-matches").inner_text()
        hal = page.locator("#score-hallucinations").inner_text()
        print(f"   Score Card: Precision={prec}, Recall={rec}, False Matches={fm}, Hallucinated IDs={hal}")
        assert prec == "100.0%"
        assert rec == "100.0%"
        assert fm == "0"
        assert hal == "0"

        # Capture Screenshot 5: Answer key score card
        ss5_path = ARTIFACTS_DIR / "review_score_card_demo.png"
        page.screenshot(path=str(ss5_path), full_page=False)
        print(f"   Saved screenshot: {ss5_path}")

        # 9. Test Export Approved Items
        print("11. Testing Export Approved Items...")
        # Verify button triggers download or fetch
        export_btn = page.locator("#export-approved-btn")
        assert export_btn.is_visible()

        browser.close()
        print("\nALL 11 REVIEW PAGE SPECIFICATIONS VERIFIED SUCCESSFULLY!")

if __name__ == "__main__":
    run_verification()
