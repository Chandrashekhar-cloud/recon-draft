# Tie-Out Rules and Reconciliation Formulas

This document details the standard bank reconciliation formulas and tie-out validation rules used by the assistant.

---

## 1. The Core Objective

The purpose of a bank reconciliation is to determine the company's **true cash balance** at the end of an accounting period by aligning two separate records:
1. **The Bank Statement**: Cash balance reported by the financial institution.
2. **The General Ledger (Books)**: Cash balance recorded in the company's accounting software.

Because of timing differences (e.g., checks in the mail, deposits clearing late) and unrecorded transactions (e.g., monthly service charges, interest earned, bank errors), the raw bank closing balance rarely equals the book closing balance.

Reconciling items are applied to each balance until both reach the same adjusted cash balance. When both balances match, the reconciliation **ties out**.

---

## 2. Standard Reconciliation Formulas

### Formula 1: Adjusted Bank Balance

$$\text{Adjusted Bank} = \text{Bank Closing} + \text{Deposits in Transit} - \text{Outstanding Checks} \pm \text{Bank Errors}$$

- **Bank Closing (`bank_closing_cents`)**: The ending balance stated on the official bank statement.
- **+ Deposits in Transit (`deposit_in_transit`)**: Cash or checks received and recorded in the company's general ledger, but not yet processed or credited by the bank by statement cutoff.
- **- Outstanding Checks (`outstanding_check`)**: Checks written and recorded on the company's books that have not yet cleared the bank account.
- **$\pm$ Bank Errors**: Errors made by the financial institution (e.g., charging an incorrect amount or debiting another customer's check to this account).

### Formula 2: Adjusted Book Balance

$$\text{Adjusted Book} = \text{Book Closing} - \text{Unbooked Bank Fees} - \text{NSF Returns} + \text{Unbooked Interest} \pm \text{Book Errors}$$

- **Book Closing (`book_closing_cents`)**: The ending balance of the cash account on the company's general ledger.
- **- Unbooked Bank Fees (`bank_fee_unbooked`)**: Service fees, wire fees, overdraft fees, or credit card processing charges that appeared on the bank statement but have not yet been posted to the general ledger.
- **- NSF Returns (`nsf_return`)**: Non-Sufficient Funds checks. Customer checks deposited earlier that bounced; the bank reversed the credit, so the company must deduct the amount from its books and reinstate the receivable.
- **+ Unbooked Interest (`interest_unbooked`)**: Interest earned credited directly by the bank that has not yet been recorded as revenue on the general ledger.
- **$\pm$ Book Errors (`transposition_error`, `duplicate_ledger`, `sign_error`)**: Arithmetic or recording mistakes made on the company's books that require correction.

---

## 3. The Tie-Out Condition

$$\text{Adjusted Bank Balance} = \text{Adjusted Book Balance}$$

$$\text{Difference} = \text{Adjusted Bank Balance} - \text{Adjusted Book Balance} = 0$$

- **Zero Tolerance**: Every tie-out must equal zero cents (`difference_cents == 0`).
- **No Plugs (Project Rule 4)**: The system may **never** create an artificial balancing entry ("plug") to force a tie-out. If an unexplained variance exists, the system must report the exact variance.
- **Deterministic Verification (Project Rule 2)**: Python code performs all arithmetic and tie-out validation. The LLM only assists with reasoning about leftover or ambiguous items.

---

## 4. Reconciling Items and Journal Entries

Reconciling items fall into two operational categories:

| Category | Side Affected | Requires Journal Entry? | Reason |
| :--- | :--- | :--- | :--- |
| **Deposits in Transit** | Bank | **No** | Already on the books; bank will clear in normal course of business. |
| **Outstanding Checks** | Bank | **No** | Already on the books; payee will deposit and bank will clear. |
| **Bank Errors** | Bank | **No** | Bank must correct their own record upon notification. |
| **Unbooked Bank Fees** | Book | **Yes** | Expense must be recorded to reflect the deduction from cash. |
| **NSF Returned Checks** | Book | **Yes** | Deduct cash and restore accounts receivable from customer. |
| **Unbooked Interest** | Book | **Yes** | Record interest income and increase cash. |
| **Book Errors** | Book | **Yes** | Adjust ledger cash to rectify prior incorrect posting. |

> **Project Rule 5**: All generated adjusting journal entries are created with status `"pending_approval"`. A human reviewer must review and approve them before they are posted to production accounting records.

---

## 5. Numerical Walkthrough (in Cents)

### Given:
- Bank Closing Balance: `$101,005.25` (`10100525` cents)
- Book Closing Balance: `$103,520.25` (`10352025` cents)

### Bank Side Adjustments:
1. Deposit in transit: `$2,500.00` (`250000` cents)
   $$\text{Adjusted Bank} = 10100525 + 250000 = 10350525\text{ cents } (\$103,505.25)$$

### Book Side Adjustments:
1. Unbooked monthly bank fee: `$15.00` (`1500` cents)
   $$\text{Adjusted Book} = 10352025 - 1500 = 10350525\text{ cents } (\$103,505.25)$$

### Tie-Out Verification:
$$\text{Difference} = 10350525 - 10350525 = 0\text{ cents}$$

Result: **Tied out successfully**.
