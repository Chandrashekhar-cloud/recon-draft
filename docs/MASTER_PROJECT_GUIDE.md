# 📘 Recon Draft — Complete Master Project & Interview Guide

---

## 🏆 1. Executive Summary (The 60-Second Interview Pitch)

> **"What is Recon Draft?"**  
> *"Recon Draft is an autonomous bank reconciliation assistant built for enterprise accounting (Brightloop Inc, September 2026).*  
>  
> *Most AI finance prototypes fail because LLMs hallucinate numbers and make calculation errors. In Recon Draft, **we never let the AI do math**.*  
>  
> *Our system operates on a 3-pillar principle:  
> 1. **Python does all arithmetic** in integer cents, eliminating rounding errors and proving the mathematical tie-out to $0.00.  
> 2. **Claude 3.5 Sonnet** only classifies exceptions (bank fees, timing carry-forwards, digit typos).  
> 3. **Human auditors** retain final review and sign-off on all proposed adjusting journal entries before anything posts to the ERP."*

---

## 📂 2. The Dataset Deep Dive: Everything Inside & Where It Lives

If the interviewer asks: **"What is your dataset, what is inside it, and where is it located?"**

### 📍 File Location on Disk:
All scenario datasets live in:
```
d:/Recon/data/variants/
```
Specifically, the primary production demo dataset is located in:
```
d:/Recon/data/variants/full/
```

### 🏢 What Company & Period Is This?
- **Company Name:** **Brightloop Inc** (A fast-growing B2B SaaS and technology services business).
- **Accounting Period:** **September 1, 2026 – September 30, 2026**.
- **Target General Ledger Account:** **Cash #1010**.
- **Nature of Data:** **100% Synthetic, authentic operational financial data** generated via `src/generate_data.py`. No real client PII is exposed.

---

### 📄 The 4 Core Files Inside Every Dataset:

| File Name | Location | Format | What It Contains |
| :--- | :--- | :--- | :--- |
| `bank.csv` | `data/variants/full/bank.csv` | 58 rows | Official monthly checking statement from the bank. |
| `ledger.csv` | `data/variants/full/ledger.csv` | 60 rows | Internal general ledger entries recorded by Brightloop's bookkeeper. |
| `notes.txt` | `data/variants/full/notes.txt` | Text notes | Client operational notes from the bookkeeper (Stripe fees, timing, bounced checks). |
| `answer_key.json` | `data/variants/full/answer_key.json` | JSON | Ground truth benchmark containing verified matches, reconciling items, and balance proofs. |

---

### 🔍 Exact Schema of the CSV Files:

#### 1. `bank.csv` (Bank Statement Side)
- **`bank_id`** (e.g. `BNK-1001`): Unique identifier assigned by the bank.
- **`date`** (e.g. `2026-09-03`): The date the transaction cleared the bank.
- **`description`** (e.g. `SOMA OFFICE SUITES RENT CHECK #401`): Bank narrative string.
- **`amount_cents`** (e.g. `-450000` = `-$4,500.00`): Debits are negative, deposits are positive.
- **`running_balance_cents`** (e.g. `4550000`): The bank account balance after that transaction cleared.
- **Starting Balance:** `$50,000.00` (5,000,000 cents)
- **Ending Balance:** `$85,573.65` (8,557,365 cents)

#### 2. `ledger.csv` (General Ledger Cash Account Side)
- **`ledger_id`** (e.g. `GL-2001`): Internal accounting journal ID.
- **`date`** (e.g. `2026-09-01`): Date recorded in the books (often 1–2 days before clearing the bank).
- **`memo`** (e.g. `Soma Office Suites Rent Check #401`): Bookkeeper description.
- **`amount_cents`** (e.g. `-450000`): Transaction amount in exact integer cents.
- **`reference`** (e.g. `401`, `STRIPE-0902`, `INV-801`): Check number, invoice number, or batch ID.
- **`type`** (`check`, `deposit`, `card`, `ach`): Payment instrument.
- **Starting Cash:** `$50,000.00`
- **Ending Cash:** `$87,490.75`

#### 3. Real-World Accounting Traps Planted in the Data:
The synthetic generator intentionally injected real-world accounting complexities:
1. **Timing Lags:** Outstanding checks mailed near month-end (`-$650.00`), deposits made after 5 PM (`+$2,800.00`).
2. **Unbooked Bank Fees:** Monthly maintenance (`-$40.00`) and wire processing (`-$87.30`) that appeared on the bank statement on Sep 30 but were never recorded in the books.
3. **NSF (Bounced) Check:** A customer check for `-$480.00` returned for non-sufficient funds.
4. **Unrecorded Interest:** `+$55.20` commercial checking interest credited by the bank on month-end.
5. **Clerical Errors:**
   - Transposition error: Bookkeeper typed `$1,450.00` instead of `$1,540.00` (`$90.00` difference).
   - Duplicate entry: A `$95.00` bill was recorded twice in the ledger.
   - Inverted sign: A vendor rebate was recorded as an expense instead of income (`$600.00` error).
6. **Ambiguity:** Two identical wire payments of `$500.00` on the same date with different invoice references.

---

## ⚙️ 3. The 4-Step Architecture Pipeline

```
[1. CSV Input]
       │
       ▼
[2. Python Pre-Matcher] ────► 53 Pairs Matched Automatically (91.4%)
       │
       ▼ (Only 9 exception items sent to LLM)
[3. Claude 3.5 Sonnet]  ────► Categorizes: Fees, Timing, Errors, Ambiguity
       │
       ▼
[4. Python Tie-Out]     ────► Calculates 2-Column Proof: Adjusted Bank == Adjusted Book ($0.00 Diff)
       │
       ▼
[5. Human Review]       ────► Auditor Approves Exceptions & Generates Signed PDF Report
```

1. **Rule #1: Integer Cents Math:** Storing `$85,573.65` as `8557365` prevents binary floating-point rounding errors (`0.1 + 0.2 != 0.3`).
2. **Rule #2: Cost Optimization:** Python pre-matches clean transactions first. Only edge cases are sent to Claude, cutting token costs by **55%**.
3. **Rule #3: Anti-Hallucination Guardrail:** Python checks every ID in Claude's output against the input CSVs. Inventing fake IDs is impossible.
4. **Rule #4: Zero Artificial Plugs:** The system never creates a "balancing entry" to force a match. If a variance cannot be proven, it explicitly says *"Cannot prove tie-out"*.

---

## 🌐 4. Website Breakdown: Every Page, Card & Output Explained

### 1. Reconcile Page (`/run`)
- **★ Recommended Demo Banner:** 1-click button that pre-selects Full Month + V2 Agent and starts the run.
- **Step 1 (Scenario Selector):** Lets you switch between Clean, Timing, Fees, Errors, Ambiguity, or Full Month.
- **Step 2 (Preview the Data):** Shows bank and ledger starting/ending balances, client notes, and collapsible raw CSV rows.
- **Step 3 (Engine Selector):**
  - **v0 Baseline:** Raw Claude prompt without tools (fails 50% of edge cases).
  - **v1 Skill:** Claude with injected accounting rules (accurate but high token usage).
  - **v2 Full System (Recommended):** Python matcher + Claude exception analyzer + Tie-out proof.
  - **Replay (Offline):** Instant local replay from verified cache with zero API tokens or latency.

---

### 2. Review Page (`/review`)
The operational screen where the auditor inspects the results.

#### Top 4 Stat Tiles:
- **Matched (53 / 91.4%):** Clean transactions paired automatically by Python.
- **Needs Review (1):** The ambiguous identical wire that required human decision.
- **Journal Entries (7):** Proposed adjustments to update the general ledger.
- **Tie-Out Difference ($0.00):** Proven mathematical equality between bank and books.

#### The Mathematical Tie-Out Proof:
```
BANK STATEMENT SIDE                     GENERAL LEDGER CASH SIDE
Ending Bank Balance:     $85,573.65     Ending Ledger Cash:      $87,490.75
(+) Deposits in Transit:  +2,800.00     (+) Unbooked Interest:       +55.20
(-) Outstanding Checks:     -650.00     (-) Unbooked Bank Fees:     -127.30
                                        (-) NSF Returned Checks:    -480.00
                                        (±) Book Clerical Errors:   +785.00
-----------------------------------     -----------------------------------
ADJUSTED BANK BALANCE:   $87,723.65     ADJUSTED BOOK BALANCE:   $87,723.65

NET TIE-OUT VARIANCE:    $0.00 (PERFECT BALANCE)
```

#### The 5 Tabs:
1. **Needs Your Review (1):** Human-in-the-loop review. Auditor clicks *"Approve Suggestion"* or *"Keep for Review"*.
2. **Matched (53):** Searchable table showing all matched pairs with date, amount, and reference IDs.
3. **Reconciling Items (9):** Breakdown of deposits in transit, outstanding checks, bank fees, and clerical errors.
4. **Journal Entries (7):** Ready-to-post double-entry bookkeeping (Debits & Credits) with status `PENDING APPROVAL`.
5. **Reviewer Memo:** Formal CPA narrative documenting balance proofs and transaction citations.

#### Action Buttons:
- **Export PDF Report:** Generates a publication-grade, signed CPA reconciliation report.
- **Export Approved Items (JSON):** Generates structured JSON payload for ERP integration (SAP, NetSuite, QuickBooks).

---

### 3. Evaluations Page (`/evals`)
The benchmark proof showing why V2 is the production-ready winner:
- **Executive Summary:** Highlights failure modes of baseline LLMs vs. the optimized V2 system.
- **Architecture Benchmarks Table:** Compares Pass Rate (100%), False Matches (0), Token Cost ($0.023), and Latency (2.9s).
- **Comprehensive Scenario Matrix:** Interactive grid across 10 scenarios. Clicking any cell opens expected answer key vs. actual model output.

---

## 🎬 5. The Step-by-Step Interview Demo Script

1. **Open the Reconcile Page (`/run`):**  
   Click the green **"▶ Run Recommended Demo"** banner. Point out the live progress steps (*"Matching → Asking Claude → Verifying Tie-Out → Writing Memo"*).
2. **Review the Proof (`/review`):**  
   Highlight the **$0.00 Tie-Out Difference**. Explain: *"Adjusted Bank equals Adjusted Book at $87,723.65. Python computed this in integer cents, not AI."*
3. **Show Human Oversight:**  
   Click the **"Needs Your Review (1)"** tab. Show the ambiguous identical wire, explain why AI shouldn't guess, and click **"Approve Suggestion"**.
4. **Download the PDF:**  
   Click **"Export PDF Report"** and open the clean 2-page executive report.
5. **Show Benchmarks (`/evals`):**  
   Show the comparison table: *"Raw Claude failed 50% of tests. Our hybrid architecture achieved 100% accuracy and cut token costs by 55%."*

---

## ❓ 6. Common Interview Questions & Answers

#### Q: "Why is the tie-out difference $0.00?"
> **A:** *"In GAAP accounting, bank balance plus deposits in transit minus outstanding checks equals general ledger cash adjusted for unrecorded fees and clerical errors. Because both sides equal $87,723.65, the variance is $0.00."*

#### Q: "Why did you use Python instead of letting Claude do the math?"
> **A:** *"LLMs are probabilistic token predictors, not calculators. They make hallucination and rounding errors. Python provides deterministic, auditable arithmetic in integer cents."*

#### Q: "Where did this dataset come from?"
> **A:** *"It is a synthetic, deterministic dataset generated by our `src/generate_data.py` script. It models Brightloop Inc for September 2026, including realistic timing lags, Stripe fee splits, unrecorded bank charges, and bookkeeper clerical errors."*

#### Q: "How does this prevent hallucinated data?"
> **A:** *"Every transaction ID returned by the LLM is checked against the raw CSV files by our Python guardrail (`src/verify.py`). If an ID does not exist in the source files, the reconciliation is rejected."*
