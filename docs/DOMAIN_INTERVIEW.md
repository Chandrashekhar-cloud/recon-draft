# Domain Rules & Accounting Guidelines

## Notice on Origin of Rules

No external interview was conducted. Do NOT invent, assume, or attribute any additional rules to an accounting person or external domain expert. All rules documented below are taken strictly and exclusively from the explicit instructions provided by the user.

---

## Explicit Accounting Rules

The following rules have been explicitly established for this reconciliation system:

1. **Reconciling Items Definition**:
   Only items that exist in the ledger but not the bank, and items that exist in the bank but not the ledger, are reconciling items.

2. **Timing Differences (No Journal Entry)**:
   Outstanding checks and deposits in transit are timing differences. They need NO journal entry.

3. **Book Adjustments (Journal Entry Required)**:
   Bank fees, interest, and NSF returns need a journal entry in the books.

4. **Transposition Errors**:
   Amounts that differ by transposed digits are suspected errors. Flag them for human review; do not match them.

5. **Ambiguous Matches**:
   Never match two items on amount alone when more than one candidate exists. Flag them as ambiguous for human review.

6. **Split / Many-to-One Matches**:
   One bank deposit can equal several ledger items. Verify that the sum matches exactly before matching.

7. **No Plugs or Suspense Entries**:
   Never create a plug or suspense entry to force the balance to work.

8. **Missing Information**:
   If a balance or input file is missing, state clearly that you cannot prove the tie-out. Do not guess or invent numbers.

9. **Journal Entry Status**:
   All proposed journal entries are drafts with status `pending_approval`.

---

## Additional Domain Rules

Additional domain rules not provided yet.
