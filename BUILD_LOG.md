# Build Log

Template for entries:
## [date time] What I did / What happened / Error text (if any) / Fix

## [2026-10-01 23:25:00] What I did / What happened / Error text (if any) / Fix
What I did: Implemented src/money.py (to_cents, fmt), tests/test_money.py, docs/SCHEMA.md, and docs/TIEOUT_RULES.md.
What happened: Ran `pytest tests/test_money.py` and encountered an import error due to missing pythonpath.
Error text: ModuleNotFoundError: No module named 'src'
Fix: Added pytest.ini configuring `pythonpath = .` and added src/__init__.py and tests/__init__.py. All 7 tests passed.

