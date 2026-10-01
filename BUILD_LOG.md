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


