# Project Rules

1. All money is stored as integer cents. Never use floats for money.
2. Python does all arithmetic, matching of exact items, tie-out math and verification. The LLM only does judgment on leftover items.
3. The LLM may never invent transaction IDs. Every ID it returns must exist in the input files.
4. The LLM may never create a "plug" entry to force a balance. If it cannot reconcile, it must say so.
5. Journal entries are always status "pending_approval". A human approves them.
6. Every number shown in the UI must come from a real run saved in results/ or cache/. Never hardcode results.
7. All data in this repo is synthetic. No real client data.
8. Keep code simple and commented in plain English.
