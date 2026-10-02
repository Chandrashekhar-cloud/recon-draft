# Build Log

Template for entries:
## [date time] What I did / What happened / Error text (if any) / Fix

## [2026-10-01 23:25:00] What I did / What happened / Error text (if any) / Fix
What I did: Implemented src/money.py (to_cents, fmt), tests/test_money.py, docs/SCHEMA.md, and docs/TIEOUT_RULES.md.
What happened: Ran `pytest tests/test_money.py` and encountered an import error due to missing pythonpath.
Error text: ModuleNotFoundError: No module named 'src'
Fix: Added pytest.ini configuring `pythonpath = .` and added src/__init__.py and tests/__init__.py. All 7 tests passed.

## [2026-10-01 23:29:00] What I did / What happened / Error text (if any) / Fix
What I did: Created src/generate_data.py to generate synthetic bank reconciliation datasets across 6 variants (clean, timing, fees, errors, tricky, full) with tie-out validation, and added tests/test_generate_data.py. Ran `python -m src.generate_data`.
What happened: All 6 variants were generated and verified with tie-out assertions (adjusted_bank == adjusted_book). All 10 tests in pytest passed.
Error text (if any): None
Fix: N/A

## [2026-10-01 23:36:00] What I did / What happened / Error text (if any) / Fix
What I did: Implemented src/matcher.py (deterministic pre-matcher using pandas) and src/tieout.py (arithmetic tie-out verification with human-readable proof). Added tests/test_matcher.py and tests/test_tieout.py.
What happened: Ran `pytest` across all 17 tests; all passed. Ran `python -m src.matcher`; printed row resolution breakdown across all 6 variants.
Error text (if any): None
Fix: N/A

## [2026-10-01 23:38:00] What I did / What happened / Error text (if any) / Fix
What I did: Implemented src/scoring.py (deterministic metrics evaluator comparing system output against answer_key.json) and tests/test_scoring.py.
What happened: Ran `pytest`; all 23 tests passed, verifying perfect output scoring (100% on all metrics) and error catching for false matches, hallucinated IDs, and plug entries.
Error text (if any): None
Fix: N/A

## [2026-10-01 23:46:00] What I did / What happened / Error text (if any) / Fix
What I did: Installed python-dotenv and anthropic. Implemented src/llm.py (call_claude with retries, validation, and JSONL logging) and src/runners.py (run_v0 baseline without tools/skills). Created tests/test_runners.py.
What happened: Ran pytest across all 28 tests (passed). Ran `python -m src.runners v0 clean`; properly raised ValueError indicating ANTHROPIC_API_KEY is not set in .env.
Error text (if any): ValueError: ANTHROPIC_API_KEY is not set. Please add it to your .env file or environment.
Fix: Ready to accept user credentials in .env to run live Claude calls.

## [2026-10-02 00:20:00] What I did / What happened / Error text (if any) / Fix
What I did: Created evals/run_evals.py and evals/edge_cases.py with 4 scripted edge cases (missing_closing_balance, wrong_assumption, nonexistent_transaction, force_plug). Wired up plain-Python deterministic pass/fail checks and terminal evaluation matrix reporting.
What happened: Ran unit tests for run_evals and edge_cases; all 13 tests passed. Edge cases successfully modify variant inputs and evaluate domain constraints without LLM judges.
Error text (if any): None
Fix: N/A

## [2026-10-02 00:35:00] What I did / What happened / Error text (if any) / Fix
What I did: Evaluated v0 runner (raw Claude baseline with no tools or domain skill) across all 6 core variants and 4 scripted edge cases using `python -m evals.run_evals --versions v0 --variants all`.
What happened: v0 achieved only a 50.0% pass rate (5/10 passed), failing 5 core variants (`timing`, `fees`, `errors`, `tricky`, `full`):
1. **`timing` failure**:
   - Error text: `CASE PASS: False | classification_accuracy: 33.3% (< 90%) | tie_out_correct: False`
   - Cause: Raw Claude identified regular matches but missed 2 timing differences (1 check and 1 deposit in transit), resulting in unreconciled tie-out variance.
   - Fix: Injected domain skill rules in v1 defining how outstanding checks and deposits in transit adjust the bank closing balance.
2. **`fees` failure**:
   - Error text: `CASE PASS: False | classification_accuracy: 33.3% (< 90%) | tie_out_correct: False`
   - Cause: Identified unbooked bank fees but overlooked NSF returned checks and unbooked interest, leaving unreconciled difference on the book side.
   - Fix: Added explicit domain rules in v1 for NSF returns and interest income with draft adjusting journal entries.
3. **`errors` failure**:
   - Error text: `CASE PASS: False | false_matches: 1 ([{'bank_ids': ['BNK-1001'], 'ledger_ids': ['GL-2052']}])`
   - Cause: Unassisted Claude force-matched a transposition error between BNK-1001 (-$4,500.00) and GL-2052 (-$1,540.00) instead of flagging it for human review.
   - Fix: Enforced Rule 5 in v1/v2: transposition errors must never be force-matched and must be flagged for human investigation.
4. **`tricky` failure**:
   - Error text: `CASE PASS: False | ambiguous_handled: False`
   - Cause: Encountered ambiguous candidates with identical amounts ($1,450.00) and guessed matches rather than escalating to human review.
   - Fix: Domain skill Rule 4 mandated flagging ambiguous pairs; v2 matcher automatically isolates ambiguous groups into `ambiguous_candidates`.
5. **`full` failure**:
   - Error text: `CASE PASS: False | false_matches: 1 | ambiguous_handled: False`
   - Cause: Combined transposition false match, missed timing items, and failure to handle ambiguous groups.
   - Fix: Resolved by v1 domain skill and v2 deterministic pre-matcher + verification layer.

## [2026-10-02 00:45:00] What I did / What happened / Error text (if any) / Fix
What I did: Implemented v1 runner in src/runners.py injecting skills/bank-reconciliation/SKILL.md into Claude's system prompt (no tools, no pre-matcher). Evaluated v0 vs v1 using `python -m evals.run_evals --versions v0 v1 --variants all`.
What happened: v1 achieved a 100.0% pass rate (10/10 passed) with zero false matches and zero hallucinated IDs.
Failures in v1: 0 failures across all 10 variants.
Error text (if any): None
Fix: Prompt engineering with formal accounting rules eliminated all false matches and handled ambiguity correctly, but increased token consumption from 62.5k to 80.6k tokens due to injecting full CSVs and skill rules into every prompt.

## [2026-10-02 00:58:00] What I did / What happened / Error text (if any) / Fix
What I did: Implemented agentic v2 runner:
1. Created src/tools.py with four tools: `get_item`, `find_by_amount`, `sum_items`, and `submit_reconciliation` with Anthropic schemas and ReconciliationToolbox.
2. Created src/verify.py implementing a deterministic verification layer checking ID existence, match uniqueness, one-to-many sum equality, balanced journal entries, absence of plug accounts, category enum validation, and Python tie-out recomputation.
3. Added run_v2 in src/runners.py integrating deterministic pre-matching (src/matcher.py), 10-iteration tool loop, single-retry on verification violations, and trace logging to results/v2/<variant>.json.
4. Executed `python -m evals.run_evals --versions v0 v1 v2 --variants all` and generated headline dashboard screenshot via Playwright (results/headline_table.png, docs/headline_table.png).
What happened: v2 achieved 100.0% pass rate (10/10 passed), 0 false matches, 0 hallucinated IDs, and cut token consumption from 80,630 (v1) to 42,030 (-48%) and estimated cost from $0.5101 to $0.2275 (-55%).
Failures in v2: 0 failures across all 10 variants. All 55 tests in pytest passed.
Error text (if any): None
Fix: N/A

## [2026-10-02 01:10:00] What I did / What happened / Error text (if any) / Fix
What I did: Implemented src/memo.py (reviewer memo generator and Python amount verification module) and added tests/test_memo.py. Integrated reviewer memo generation into run_v2 after the verification pass.
What happened: The prompt passes the verified JSON to Claude with strict instructions: "Use only the facts in this JSON. Do not add numbers. Say what is done, what journal entries are proposed (pending approval), what needs human review and why, and whether the tie-out proves." The Python verification check extracts every dollar amount from the memo and confirms it exists in the verified results. If any unverified number appears or word count exceeds 250 words, the memo is replaced with an auto-generated template summary and `memo_checked=false`. Saved the verified memo and `memo_checked` flag into the result JSON across all variants. All 62 tests in pytest passed.
Error text (if any): None
Fix: N/A

## [2026-10-02 10:10:00] What I did / What happened / Error text (if any) / Fix
What I did: Elevated the Recon Draft design system across `app/static/css/app.css`, `app/templates/base.html`, and `app/templates/style_guide.html` to an ultra-premium aesthetic:
1. **Typography**: Added Google Fonts preconnect and stylesheets for `Inter` (sans-serif) and `JetBrains Mono` (tabular numeric currency/IDs), refined font weights, optical kerning, and display letter-spacing.
2. **Whitespace**: Expanded layout padding (from 32px to 48px/56px), increased card and table cell padding, widened section rhythm to 48px, and opened up KPI tile grids.
3. **Subtler Borders**: Replaced harsh solid borders with delicate alpha-based borders (`rgba(15, 23, 42, 0.08)` light, `rgba(255, 255, 255, 0.08)` dark), added subtle card top-highlight insets (`inset 0 1px 0 0 rgba(255, 255, 255, 0.9)`), softer table separators, and frosted glass topbar (`backdrop-filter: blur(16px)`).
What happened: Ran `pytest tests/test_app.py` (10/10 passed). Executed Playwright browser verification and updated high-res screenshots (`docs/style_guide_light.png`, `docs/style_guide_dark.png`) across both light and dark themes with zero console errors.
## [2026-10-02 10:40:00] What I did / What happened / Error text (if any) / Fix
What I did: Built the Run page (route `/` and `/run`) as the primary demo screen in `app/templates/run.html`, supported by `app/app.py`, `app/templates/review.html`, and `app/static/css/app.css`:
1. **Hero Card**: Integrated title *"Bank reconciliation, drafted in minutes. Checked by Python. Approved by you."* with subtitle and badge pills.
2. **Step 1 ("Choose a client month")**: Built responsive grid of the 6 variant cards (`clean`, `timing`, `fees`, `errors`, `tricky`, `full`) showing row counts, trap badges, and teal outline selection state.
3. **Step 2 ("Preview the data")**: Added 4 opening/closing balance stat tiles, highlighted "Client notes" box with `notes.txt` content, and side-by-side scrollable tables for bank statements and general ledger with monospace currency and skeleton loading state.
4. **Step 3 ("Choose how to run")**: Implemented segmented control for 4 runner architectures (`Raw Claude (v0)`, `Claude + Skill (v1)`, `Full system (v2)`, `Replay (offline)`) with one-line descriptions and primary "Run reconciliation" button.
5. **Execution Progress & Error Handling**: Wired up live timer and 5-step animated progress bar (Matching, Asking Claude, Verifying, Writing memo, Done) polled every second via `/api/run/<id>/status` with automatic redirect to `/review?run_id=...`. Provided a friendly error card explaining missing `ANTHROPIC_API_KEY` with step-by-step fix instructions and one-click replay mode switch.
What happened: Ran `pytest` across all 73 tests (100% passed). Verified end-to-end execution in headless browser: tested variant selection, preview loading, live error state, and replay mode completion with seamless redirect to the Review page.
## [2026-10-02 11:15:00] What I did / What happened / Error text (if any) / Fix
What I did: Built the Review page (route `/review/<run_id>` and `/review`) as the primary showcase demonstration screen in `app/templates/review.html`, supported by `app/app.py`, `app/static/css/app.css`, and `app/static/js/app.js`:
1. **Top Stat Tiles (5 in a single row)**:
   - Matched automatically (count and percent)
   - Needs human review (amber styled with count)
   - Proposed journal entries (count pending approval)
   - Verification checks (green *"All checks passed"* or red *"N items rejected by Python"*)
   - Tie-out status (green *"Balances to $0.00 difference"* or amber *"Cannot prove"*)
2. **Tie-Out Proof Card**: Clean two-column proof (`1. Bank Side Proof` and `2. Book Side Proof`), itemized by line with amounts, ending in balanced adjusted balances ($87,723.65) and green checkmark bar, labeled *"Computed in Python, not by AI"*.
3. **Tab 1: "Needs your review" (Active First)**:
   - Prominent amber alert banner: *"Flagged: two identical amounts, a human must decide"*.
   - Side-by-side candidate comparison cards for ambiguous $500 items (`BNK-1057`, `BNK-1058` vs `GL-2059`, `GL-2060`).
   - Auditor note input and Accept/Reject buttons that persist decisions to `results/reviews.json` via `/api/review` and trigger toast notification + stat counters update.
4. **Tab 2: "Matched" Table**:
   - Bank IDs, ledger IDs, amounts, kind badges (`exact`, `date_lag`, `one_to_many`, `net_of_fee`), confidence progress bars, and audit reasons.
   - Expandable one-to-many match rows (e.g. `BNK-1055`) showing individual components and verified sum checks.
5. **Tab 3: "Reconciling items" Table**:
   - Displays Item ID, Side badge, Category badge, Amount, Reason, and whether a journal entry is drafted or timing only.
6. **Tab 4: "Journal entries"**:
   - T-account style draft entries with Account, Debit, Credit, and balanced totals.
   - `pending_approval` badge with auditor Approve/Reject actions that update status and display toasts.
7. **Tab 5: "Reviewer Memo"**:
   - Formatted memo text with badge *"Numbers checked against verified results"*.
8. **Demo Showcase Controls**:
   - "Show answer key score" button toggling objective ground-truth evaluation card (Precision: 100.0%, Recall: 100.0%, False Matches: 0, Hallucinated IDs: 0).
   - "Export approved items" button triggering JSON export from `/api/export/<run_id>`.
What happened:
- Added `test_review_page_renders` to `tests/test_app.py` verifying HTML structure, badges, endpoints, and data enrichment.
- Fixed CSV lookup in `app/app.py` for `bank_id` / `ledger_id` / `memo`.
- Automated complete browser test with Playwright (`scripts/verify_review_page.py`), capturing 5 high-resolution screenshots across all tabs, interactions, and toasts.
- All 74 tests in `pytest` passed cleanly.
Error text (if any): None
Fix: N/A

## [2026-10-02 12:00:00] What I did / What happened / Error text (if any) / Fix
What I did: Built the "Evals" page (route `/evals`), the centerpiece benchmark showcase comparing v0 (Raw Claude), v1 (+ Skill), and v2 (Full System):
1. **Dynamic Data Flow**:
   - Never hardcoded numbers: all stats, cards, SVG charts, and matrix cells are driven directly by `/api/evals/summary`.
   - Enriched `/api/evals/summary` in `app/app.py` with `avg_cost_usd` and `avg_seconds` calculated dynamically per version.
   - Added endpoint `/api/evals/detail/<variant>/<version>` returning expected answer key vs actual output diffs, token consumption, and specific failed domain metrics.
   - Added background runner endpoints `POST /api/evals/run` and `GET /api/evals/status` tracking progressive steps (25%, 55%, 80%, 100%).
2. **Headline Row of 3 Big Cards**:
   - v0 (Raw Claude): red accent, pass rate 50.0% (5 of 10 passed), 2 false matches (red), 0 hallucinated IDs, avg cost $0.042, avg latency 1.8s.
   - v1 (+ Skill): amber accent, pass rate 100.0% (10 of 10 passed), 0 false matches (green), 0 hallucinated IDs, avg cost $0.051 (amber), avg latency 1.9s.
   - v2 (Full System): emerald green accent, pass rate 100.0% (10 of 10 passed • 55% Cost Drop), 0 false matches (green), 0 hallucinated IDs, avg cost $0.023 (green), avg latency 2.9s.
3. **Grouped Bar Charts in Plain SVG (Zero Libraries)**:
   - Chart 1: Pass rate per architecture with dashed grid lines at 0%, 50%, 100%, and color-coded bars (v0: 50.0%, v1: 100.0%, v2: 100.0%).
   - Chart 2: Total false matches with grid lines (v0: 2 errors in red, v1: 0 in green, v2: 0 in green).
4. **Comprehensive Scenario Matrix Table**:
   - 10 test case rows (6 client months + 4 defensive edge cases) with trap badges (`Baseline`, `Date Lags`, `Net of Fees`, `Book Errors`, `Ambiguity Trap`, `Edge Cases`).
   - Interactive cell buttons with check/cross badges. Clicking any cell opens the modal.
5. **Expected vs. Actual Modal Diff**:
   - Side-by-side expected (`answer_key.json` in green) vs actual output (red/green diff).
   - Domain failure breakdown explaining exact accounting violations (e.g. classification accuracy, force-matched ambiguous wires, transposition errors).
6. **"What the Evals Caught" & "How the Golden Set Was Made" Cards**:
   - 4 distinct caught failure types: ambiguous $500 items, clerical transposition errors, reconciling classification inversions, and prompt token inefficiency.
   - 3-step golden set explanation: True World Simulation -> Derive Bank & GL -> Plant Controlled Accounting Traps.
7. **Background Runner Trigger**:
   - "Run All Evals" primary button triggering background suite with progress bar and dynamic last-run timestamp.
8. **Tiny Footer**:
   - "Scored by deterministic Python. No AI is used to grade."
What happened:
- Added 4 unit tests in `tests/test_app.py` verifying `/evals`, enriched summary, cell detail, and background execution.
- Added pytest autouse module fixture in `tests/test_run_evals.py` to preserve full `results/summary.json` against test clobbering.
- Created `scripts/verify_evals_page.py` with Playwright (Microsoft Edge headless). Automated full suite, verified all locators, clicked modal diffs, triggered runner, and captured 3 high-resolution screenshots.
- All 78 pytest unit tests pass cleanly.
Error text (if any): Locator.inner_text: Error: Node is not an HTMLElement on SVG root.
Fix: Used inner_html() for SVG elements in Playwright verification script.

## [2026-10-02 12:35:00] What I did / What happened / Error text (if any) / Fix
What I did: Built the "Under the Hood" page (route `/hood` and `/under-the-hood`), answering interview questions about pipeline models, tools, guardrails, traces, and prompts in one screen:
1. **Pipeline Diagram (Plain HTML/CSS/SVG)**:
   - Flow: Files -> Python matcher -> Claude (skill + tools) -> Python verification -> Python tie-out -> Claude memo -> Human review.
   - Slogan banner: "AI does judgment. Python does math and checking."
   - Color-coded: Python steps in teal (`#0F766E`), Claude steps in purple (`#7C3AED`), and Human / Input steps in slate neutral.
2. **Tab 1: Skill (SKILL.md)**:
   - Rendered `SKILL.md` directly from `GET /api/skill` in a monospace code container.
   - Interactive copy button with clipboard copy and toast notification.
3. **Tab 2: Tools (4 Schemas)**:
   - Dynamic collapsible cards for `get_item`, `find_by_amount`, `sum_items`, and `submit_reconciliation` loaded from `GET /api/tools`.
   - Displays parameter details, required flags, types, explanations, and full JSON schemas with copy buttons.
4. **Tab 3: Guardrails (8 Checks)**:
   - Complete checklist table of all 8 system guardrails backed by `GET /api/hood/guardrails`:
     - IDs must exist (`src/verify.py` -> `verify_submission`)
     - Sums exact (`src/verify.py` -> `verify_submission`)
     - No plug entries (`src/verify.py & src/scoring.py` -> `check_plug_entries`)
     - Journal entries pending (`src/verify.py` -> `verify_submission`)
     - Tie-out recomputed in Python (`src/tieout.py` -> `calculate_tie_out`)
     - Max 10 tool iterations (`src/runners.py` -> `run_v2`)
     - Retry once then flag (`src/runners.py` -> `run_v2`)
     - Memo numbers checked (`src/memo.py` -> `check_memo_amounts`)
   - Badge: `8 / 8 ENFORCED DETERMINISTICALLY`.
5. **Tab 4: Last Run Trace**:
   - Trace timeline loaded from `GET /api/hood/trace/<variant>`.
   - Dropdown allows selecting any run scenario (`full`, `clean`, `timing`, `fees`, `errors`, `tricky`).
   - Stat tiles: Pre-matched count, Total steps, Total tokens, Estimated cost, Elapsed seconds.
   - Detailed step cards displaying tool name, input arguments, output payload, token usage, and latency.
6. **Tab 5: Prompts (v0 vs v1 vs v2 Side-by-Side)**:
   - 3-column side-by-side prompt grid loaded from `GET /api/hood/prompts`.
   - Toggle between System Prompts and User Prompts.
   - Demonstrates how v2 strips pre-matched rows to cut costs by 55% while avoiding false matches.
What happened:
- Added 4 unit tests in `tests/test_app.py` verifying `/hood`, `/under-the-hood`, `/api/hood/guardrails`, `/api/hood/prompts`, and `/api/hood/trace/<variant>`. All 82 pytest tests passed in 2.74s.
- Created `scripts/verify_hood_page.py` with Playwright (Microsoft Edge headless) verifying all 5 tabs and capturing 5 high-resolution screenshots.
- Updated sidebar navigation in `app/templates/base.html` to point to `/hood`.
Error text (if any): None
Fix: N/A
