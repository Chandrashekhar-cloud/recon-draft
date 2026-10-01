# Data Schemas

This document defines the exact file formats and data schemas used across all variants and evaluation datasets in the reconciliation project.

---

## 1. `bank.csv`

The bank statement export file. Each row represents a single bank transaction.

### Columns

| Column Name | Type | Description |
| :--- | :--- | :--- |
| `bank_id` | String | Unique bank transaction identifier (e.g., `BNK-1001`). |
| `date` | String | Transaction date formatted as `YYYY-MM-DD`. |
| `description` | String | Payee or transaction memo provided by the bank. |
| `amount_cents` | Integer | Transaction amount in cents. **Positive = money in** (deposits/credits), **Negative = money out** (withdrawals/debits). |
| `running_balance_cents` | Integer | The bank account's running balance in integer cents after the transaction posted. |

### Example

```csv
bank_id,date,description,amount_cents,running_balance_cents
BNK-1001,2026-10-01,STRIPE PAYOUT,154025,10154025
BNK-1002,2026-10-02,CHECK #4012,-52000,10102025
BNK-1003,2026-10-03,MONTHLY SERVICE FEE,-1500,10100525
```

---

## 2. `ledger.csv`

The company's general ledger (cash account) journal export. Each row represents a recorded cash transaction.

### Columns

| Column Name | Type | Description |
| :--- | :--- | :--- |
| `ledger_id` | String | Unique general ledger record identifier (e.g., `GL-2001`). |
| `date` | String | Posting or transaction date formatted as `YYYY-MM-DD`. |
| `memo` | String | Description of the transaction recorded in accounting software. |
| `amount_cents` | Integer | Transaction amount in cents. **Positive = cash increase** (cash debit), **Negative = cash decrease** (cash credit). |
| `reference` | String | Check number, invoice number, payout ID, or external reference string. |
| `type` | String | Transaction classification: `check`, `deposit`, `ach`, `card`, `fee`, `transfer`, `other`. |

### Example

```csv
ledger_id,date,memo,amount_cents,reference,type
GL-2001,2026-09-30,Stripe Gross Sales,154025,STRIPE-OCT-01,deposit
GL-2002,2026-10-01,Acme Office Supplies,-52000,4012,check
GL-2003,2026-10-02,Client Retainer Deposit,250000,INV-8891,deposit
```

---

## 3. `notes.txt`

Short contextual notes from the client or bookkeeper written in plain English. These provide real-world domain context that cannot be inferred solely from raw numbers, such as payout timing, merchant processor fee deduction policies, or uncashed check notices.

### Example

```text
Stripe payouts arrive net of fees.
Payroll ACH is initiated on the 15th and posts 1-2 business days later.
Check #4015 was written on Oct 28 to Vendor Co and has not cleared yet.
```

---

## 4. `answer_key.json`

The ground-truth reconciliation solution against which algorithms, pipelines, and evaluation runs are scored.

### JSON Structure

```json
{
  "variant": "string",
  "period_start": "YYYY-MM-DD",
  "period_end": "YYYY-MM-DD",
  "balances": {
    "bank_opening_cents": 10000000,
    "bank_closing_cents": 10100525,
    "book_opening_cents": 10000000,
    "book_closing_cents": 10352025
  },
  "matches": [
    {
      "bank_ids": ["BNK-1001"],
      "ledger_ids": ["GL-2001"],
      "kind": "exact"
    }
  ],
  "reconciling_items": [
    {
      "item_id": "GL-2003",
      "side": "ledger",
      "category": "deposit_in_transit",
      "amount_cents": 250000,
      "needs_journal_entry": false
    },
    {
      "item_id": "BNK-1003",
      "side": "bank",
      "category": "bank_fee_unbooked",
      "amount_cents": -1500,
      "needs_journal_entry": true
    }
  ],
  "ambiguous_groups": [
    {
      "bank_ids": ["BNK-1004"],
      "ledger_ids": ["GL-2004", "GL-2005"],
      "reason": "Multiple ledger transactions share the same dollar amount and date range without unique reference."
    }
  ],
  "tie_out": {
    "adjusted_bank_cents": 10350525,
    "adjusted_book_cents": 10350525,
    "difference_cents": 0
  }
}
```

### Field Definitions

#### Top-level Attributes
- `variant` *(string)*: Name or identifier of the variant scenario (e.g., `variant_01_standard`).
- `period_start` *(string)*: Start date of the reconciliation period (`YYYY-MM-DD`).
- `period_end` *(string)*: End date of the reconciliation period (`YYYY-MM-DD`).

#### `balances` Object
- `bank_opening_cents` *(int)*: Bank statement starting balance in cents.
- `bank_closing_cents` *(int)*: Bank statement ending balance in cents.
- `book_opening_cents` *(int)*: General ledger cash starting balance in cents.
- `book_closing_cents` *(int)*: General ledger cash ending balance in cents.

#### `matches` Array
List of matched transaction pairs or groupings between bank and ledger.
- `bank_ids` *(array of strings)*: List of matching `bank_id` identifiers.
- `ledger_ids` *(array of strings)*: List of matching `ledger_id` identifiers.
- `kind` *(string enum)*: Match classification:
  - `exact`: Exact amount and matching date / reference.
  - `date_lag`: Exact amount with reasonable business-day timing lag.
  - `one_to_many`: One bank batch corresponding to multiple ledger entries (or vice versa).
  - `net_of_fee`: Payout arrives net of transaction fees.

#### `reconciling_items` Array
List of items that explain the variance between bank closing and book closing balances.
- `item_id` *(string)*: Identifier of the bank (`bank_id`) or ledger (`ledger_id`) transaction.
- `side` *(string enum)*:
  - `bank`: Item appears on the bank statement.
  - `ledger`: Item appears on the general ledger.
- `category` *(string enum)*:
  - `outstanding_check`: Check issued on books but not yet cleared at bank.
  - `deposit_in_transit`: Deposit recorded on books but not yet credited by bank.
  - `bank_fee_unbooked`: Bank service charge / fee appearing only on bank statement.
  - `interest_unbooked`: Interest earned appearing only on bank statement.
  - `nsf_return`: Non-sufficient funds returned check deducted by bank.
  - `duplicate_ledger`: Erroneous duplicate entry posted to ledger.
  - `transposition_error`: Digits reversed when recording transaction (e.g. 54 vs 45).
  - `sign_error`: Amount recorded with inverted sign (debit instead of credit).
  - `prior_period_item`: Item belonging to a prior accounting period.
- `amount_cents` *(int)*: Reconciling dollar amount in integer cents.
- `needs_journal_entry` *(boolean)*:
  - `true`: Requires an adjusting journal entry to bring books into balance (status will be `pending_approval`).
  - `false`: Timing difference requiring no book adjustment.

#### `ambiguous_groups` Array
Groups of transactions requiring human judgment or disambiguation.
- `bank_ids` *(array of strings)*: Bank identifiers involved in the ambiguity.
- `ledger_ids` *(array of strings)*: Ledger identifiers involved in the ambiguity.
- `reason` *(string)*: Explanation of why automatic matching could not uniquely resolve the pair.

#### `tie_out` Object
Final mathematical verification that reconciles both sides.
- `adjusted_bank_cents` *(int)*: Final adjusted bank balance in integer cents.
- `adjusted_book_cents` *(int)*: Final adjusted book balance in integer cents.
- `difference_cents` *(int)*: Must be exactly `0` (`adjusted_bank_cents - adjusted_book_cents`).
