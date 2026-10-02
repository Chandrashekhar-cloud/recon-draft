import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\chand\.gemini\antigravity-ide\brain\2afb1203-f8fa-4138-a4eb-7a98245b3593"

def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 920})
        page = context.new_page()

        print("Navigating to http://127.0.0.1:5000/hood...")
        page.goto("http://127.0.0.1:5000/hood", wait_until="networkidle")
        time.sleep(1)

        # 1. Pipeline Diagram Verification
        banner = page.locator(".pipeline-slogan").inner_text()
        print(f"Pipeline Slogan: {banner}")
        assert "AI does judgment. Python does math and checking." in banner

        step_nodes = page.locator(".pipeline-step-node")
        print(f"Pipeline step count: {step_nodes.count()}")
        assert step_nodes.count() >= 7, f"Expected 7 pipeline steps, found {step_nodes.count()}"

        # Verify color coding classes
        python_steps = page.locator(".pipeline-step-python")
        claude_steps = page.locator(".pipeline-step-claude")
        print(f"Python steps count: {python_steps.count()}, Claude steps count: {claude_steps.count()}")
        assert python_steps.count() >= 3, f"Expected >= 3 Python steps, found {python_steps.count()}"
        assert claude_steps.count() >= 2, f"Expected >= 2 Claude steps, found {claude_steps.count()}"

        # Save Overview Screenshot
        overview_path = os.path.join(ARTIFACT_DIR, "hood_page_pipeline_overview.png")
        page.screenshot(path=overview_path, full_page=True)
        print(f"Saved pipeline overview screenshot to {overview_path}")

        # 2. Tab "Skill" Verification
        skill_box = page.locator("#skill-content-box")
        page.wait_for_selector("#skill-content-box")
        skill_text = skill_box.inner_text()
        assert "Bank Reconciliation Skill" in skill_text
        assert "Classification rules" in skill_text
        assert "Hard rules" in skill_text
        print("Tab Skill content verified.")

        # Test Copy SKILL.md button
        copy_skill_btn = page.locator("#btn-copy-skill")
        copy_skill_btn.click()
        time.sleep(0.5)

        # 3. Tab "Tools" Verification
        print("Switching to Tools tab...")
        page.locator("#btn-tab-tools").click()
        time.sleep(0.6)

        tool_cards = page.locator(".tool-collapsible-card")
        print(f"Tool cards count: {tool_cards.count()}")
        assert tool_cards.count() == 4, f"Expected 4 tool schemas, found {tool_cards.count()}"

        # Verify tool names
        tools_text = page.locator("#tools-container").inner_text()
        assert "get_item" in tools_text
        assert "find_by_amount" in tools_text
        assert "sum_items" in tools_text
        assert "submit_reconciliation" in tools_text

        # Click the 2nd tool card to expand it
        page.locator(".tool-header-btn").nth(1).click()
        time.sleep(0.4)

        # Save Tools tab screenshot
        tools_path = os.path.join(ARTIFACT_DIR, "hood_tools_tab.png")
        page.screenshot(path=tools_path)
        print(f"Saved tools tab screenshot to {tools_path}")

        # 4. Tab "Guardrails" Verification
        print("Switching to Guardrails tab...")
        page.locator("#btn-tab-guardrails").click()
        time.sleep(0.6)

        guardrail_rows = page.locator("#guardrails-tbody tr")
        print(f"Guardrail rows count: {guardrail_rows.count()}")
        assert guardrail_rows.count() == 8, f"Expected 8 guardrails, found {guardrail_rows.count()}"

        guardrails_html = page.locator("#guardrails-tbody").inner_text()
        assert "Transaction IDs Must Exist" in guardrails_html
        assert "One-to-Many Sums Exact" in guardrails_html
        assert "No Plug Entries Permitted" in guardrails_html
        assert "Journal Entries Must Be Pending" in guardrails_html
        assert "Tie-Out Recomputed in Python" in guardrails_html
        assert "Max 10 Tool Iterations" in guardrails_html
        assert "Retry Once Then Flag" in guardrails_html
        assert "Reviewer Memo Numbers Checked" in guardrails_html
        assert "src/verify.py" in guardrails_html
        assert "src/tieout.py" in guardrails_html
        assert "src/runners.py" in guardrails_html
        assert "src/memo.py" in guardrails_html

        # Save Guardrails screenshot
        guardrails_path = os.path.join(ARTIFACT_DIR, "hood_guardrails_tab.png")
        page.screenshot(path=guardrails_path)
        print(f"Saved guardrails tab screenshot to {guardrails_path}")

        # 5. Tab "Last run trace" Verification
        print("Switching to Last Run Trace tab...")
        page.locator("#btn-tab-trace").click()
        time.sleep(0.6)

        trace_prematched = page.locator("#trace-prematched").inner_text()
        trace_steps = page.locator(".trace-step-item")
        print(f"Trace prematched: {trace_prematched}, steps count: {trace_steps.count()}")
        assert "49" in trace_prematched
        assert trace_steps.count() >= 1

        # Test selecting another variant in dropdown
        select = page.locator("#trace-variant-select")
        select.select_option("timing")
        time.sleep(0.6)
        trace_timing_steps = page.locator(".trace-step-item")
        print(f"Trace timing steps count: {trace_timing_steps.count()}")
        assert trace_timing_steps.count() >= 1

        # Save Trace tab screenshot
        trace_path = os.path.join(ARTIFACT_DIR, "hood_trace_tab.png")
        page.screenshot(path=trace_path)
        print(f"Saved trace tab screenshot to {trace_path}")

        # 6. Tab "Prompts" Verification
        print("Switching to Prompts tab...")
        page.locator("#btn-tab-prompts").click()
        time.sleep(0.6)

        prompt_cards = page.locator(".prompt-col-card")
        print(f"Prompt columns count: {prompt_cards.count()}")
        assert prompt_cards.count() == 3, f"Expected 3 columns (v0, v1, v2), found {prompt_cards.count()}"

        prompts_text = page.locator("#prompts-grid-container").inner_text()
        assert "v0 (Raw Claude)" in prompts_text
        assert "v1 (Claude + Skill)" in prompts_text
        assert "v2 (Full System)" in prompts_text

        # Test switching to User Prompts view
        user_view_btn = page.locator("#btn-prompt-view-user")
        user_view_btn.click()
        time.sleep(0.4)
        user_prompts_text = page.locator("#prompts-grid-container").inner_text()
        assert "Pre-matched count: 49 pairs" in user_prompts_text or "REMOVED FROM CONTEXT" in user_prompts_text

        # Save Prompts tab screenshot
        prompts_path = os.path.join(ARTIFACT_DIR, "hood_prompts_tab.png")
        page.screenshot(path=prompts_path)
        print(f"Saved prompts tab screenshot to {prompts_path}")

        # 7. Also verify route /under-the-hood aliases properly
        print("Checking alias route /under-the-hood...")
        page.goto("http://127.0.0.1:5000/under-the-hood", wait_until="networkidle")
        assert "Under the Hood" in page.locator("h1").inner_text()

        browser.close()
        print("All Under the Hood assertions and screenshots verified successfully!")

if __name__ == "__main__":
    verify()
