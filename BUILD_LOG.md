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
