---
name: bank-reconciliation
description: Reconcile bank statements against general ledger cash records using explicit accounting rules.
---

# Bank Reconciliation Skill

## When to use this skill
Use this skill when you need to reconcile a bank statement against general ledger cash accounts, identify matches, find reconciling items, create draft adjusting journal entries, and check the balance tie-out.

## Inputs you will receive
- Bank statement data (transactions with IDs, dates, descriptions, amounts in cents, and balances).
- General ledger data (transactions with IDs, dates, memos, amounts in cents, and references).
- Optional notes or user instructions.

## Step-by-step process
1. Read the bank statement and general ledger transactions.
2. Match transactions between the bank and the ledger. One bank deposit can equal several ledger items; verify the sum matches exactly before matching.
3. Identify items that exist in the ledger but not the bank, and in the bank but not the ledger. These are your reconciling items.
4. Classify reconciling items into timing differences or book adjustments.
5. Create draft journal entries for items requiring adjustments in the books.
6. Check whether the balances tie out. If a balance or file is missing, report that you cannot prove the tie-out.
7. Return the final structured output.

## Classification rules
- **Reconciling items**: Only items in the ledger but not the bank, and in the bank but not the ledger, are reconciling items.
- **Timing differences**: Outstanding checks and deposits in transit are timing differences. They need NO journal entry.
- **Book adjustments**: Bank fees, interest, and NSF returns need a journal entry in the books.

## Hard rules
- Never create a plug or suspense entry to make the balance work.
- If a balance or file is missing, say you cannot prove the tie-out. Do not guess.
- Never match two items on amount alone when more than one candidate exists. Flag as ambiguous.
- Amounts that differ by transposed digits are suspected errors. Flag them, do not match.
- One bank deposit can equal several ledger items. Verify the sum exactly before matching.
- Journal entries are drafts with status `pending_approval`.

## When to flag for a human
- When more than one candidate exists with the same amount (ambiguous match). Do not match on amount alone.
- When transaction amounts differ by transposed digits (suspected errors). Do not match.

## Output format
Return a JSON object with the following fields:
```json
{
  "matches": [
    {"bank_ids": ["..."], "ledger_ids": ["..."], "confidence": 1.0, "reason": "..."}
  ],
  "reconciling_items": [
    {"item_id": "...", "side": "bank|ledger", "category": "...", "amount_cents": 0, "reason": "..."}
  ],
  "flagged_for_human": [
    {"ids": ["..."], "reason": "..."}
  ],
  "proposed_journal_entries": [
    {
      "description": "...",
      "lines": [{"account": "...", "debit_cents": 0, "credit_cents": 0}],
      "status": "pending_approval"
    }
  ],
  "tie_out": {
    "adjusted_bank_cents": 0,
    "adjusted_book_cents": 0,
    "difference_cents": 0,
    "can_prove": true
  },
  "memo": "..."
}
```

## Two worked examples using made-up IDs

### Example 1: Standard match and an outstanding check (timing difference)
- **Inputs**:
  - Bank has deposit `BNK-101` for $500.00 (50000 cents).
  - Ledger has deposit `GL-501` for $500.00 (50000 cents) and check `GL-502` for -$120.00 (-12000 cents) not found in bank statement.
- **Actions**:
  - Match `BNK-101` with `GL-501`.
  - Identify `GL-502` as in the ledger but not the bank. Classify as outstanding check (timing difference).
  - No journal entry is created for `GL-502`.
- **Output**:
  - `matches`: `[{"bank_ids": ["BNK-101"], "ledger_ids": ["GL-501"]}]`
  - `reconciling_items`: `[{"item_id": "GL-502", "side": "ledger", "category": "outstanding_check", "amount_cents": -12000}]`
  - `proposed_journal_entries`: `[]`

### Example 2: Bank fee and ambiguous match candidates
- **Inputs**:
  - Bank has fee `BNK-102` for -$25.00 (-2500 cents) not in ledger.
  - Bank has deposit `BNK-103` for $300.00 (30000 cents).
  - Ledger has two separate entries for $300.00: `GL-503` (30000 cents) and `GL-504` (30000 cents).
- **Actions**:
  - Identify `BNK-102` as in the bank but not the ledger. Classify as bank fee. Create draft journal entry with status `pending_approval`.
  - For `BNK-103`, two candidates exist (`GL-503` and `GL-504`). Do not match on amount alone; flag all three IDs for human review.
- **Output**:
  - `reconciling_items`: `[{"item_id": "BNK-102", "side": "bank", "category": "bank_fee", "amount_cents": -2500}]`
  - `flagged_for_human`: `[{"ids": ["BNK-103", "GL-503", "GL-504"], "reason": "Ambiguous candidates with identical amounts"}]`
  - `proposed_journal_entries`: `[{"description": "Record bank fee", "status": "pending_approval", "lines": [{"account": "Bank Fees", "debit_cents": 2500, "credit_cents": 0}, {"account": "Cash", "debit_cents": 0, "credit_cents": 2500}]}]`
