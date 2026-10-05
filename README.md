# Recon Draft ⚖️
### Autonomous Bank Reconciliation Assistant &bull; Built for Review

[![Tests Passing](https://img.shields.io/badge/Tests-82%2F82%20Passing-emerald?style=flat-square&logo=pytest)](tests/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python)](requirements.txt)
[![Claude 3.5 Sonnet](https://img.shields.io/badge/Model-Claude%203.5%20Sonnet-purple?style=flat-square)](src/runners.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-gray?style=flat-square)](LICENSE)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Render-teal?style=flat-square&logo=render)](https://recon-draft-s0tm.onrender.com)

> **"Python does the math. Claude does the judgment. Humans approve the entries."**

**Recon Draft** is an autonomous bank reconciliation system designed for enterprise accounting (Brightloop Inc, September 2026). It solves a fundamental flaw in existing AI finance tools: **LLMs make arithmetic hallucinations, rounding errors, and create fake "plug" entries to force balances.**

Instead of letting an AI perform arithmetic, Recon Draft uses a **hybrid decoupled architecture**: a deterministic Python engine handles 100% of calculations in exact integer cents, Claude 3.5 Sonnet classifies edge-case exceptions, and a human auditor retains final approval on all adjusting journal entries.

---

## 🌐 Live Web Application

- **Live URL:** [https://recon-draft-s0tm.onrender.com](https://recon-draft-s0tm.onrender.com)
- **Primary Demo:** [https://recon-draft-s0tm.onrender.com/run](https://recon-draft-s0tm.onrender.com/run) *(Click "▶ Run Reconciliation")*
- **Architecture Benchmarks:** [https://recon-draft-s0tm.onrender.com/evals](https://recon-draft-s0tm.onrender.com/evals)

---

## 🏛️ System Architecture

<pre>
1. CSV Ingestion ───────► bank.csv (58 rows) &amp; ledger.csv (60 rows) in Integer Cents
        │
        ▼
2. Python Pre-Matcher ──► 53 Pairs Auto-Matched (91.4%) &bull; Zero API Cost
        │
        ▼ (Only remaining 9 exception items sent to LLM)
3. Claude 3.5 Sonnet  ──► Classifies: Fees, Timing, Clerical Typos, Ambiguities
        │
        ▼
4. Python Tie-Out ──────► GAAP Two-Column Proof: Adjusted Bank == Adjusted Book ($0.00 Diff)
        │
        ▼
5. Human Review &amp; PDF ──► Auditor Approves Exceptions &amp; Generates Signed CPA Report
</pre>

### Core Architectural Guarantees:
1. **Integer Cents Representation:** All monetary values are strictly parsed into integer cents (e.g. `$85,573.65` = `8557365`). Floating-point math is forbidden, eliminating binary float errors (`0.1 + 0.2 != 0.3`).
2. **Deterministic Pre-Matching:** Python pairs clean 1-to-1 transactions using exact date-window and amount hashes, **slashing LLM token costs by 55%**.
3. **Anti-Hallucination Guardrails (`src/verify.py`):** Every ID in Claude's output is cross-referenced against source CSV files. Fabricating fake transaction IDs is impossible.
4. **Zero Artificial Plugs:** The engine is strictly prohibited from inventing balancing entries. If numbers do not tie out, the system explicitly reports a variance.
5. **Human-in-the-Loop Oversight:** All proposed adjusting journal entries carry status `PENDING_APPROVAL`.

---

## ✨ Key Features

- **⚡ 1-Click Reconciliation:** Pre-configures the Full Month scenario (118 records) and executes the end-to-end pipeline in seconds.
- **⚖️ Two-Column Mathematical Tie-Out Proof:**
  - **Adjusted Bank Balance:** `$85,573.65` + `$2,800.00` (Deposits in Transit) - `$650.00` (Outstanding Checks) = **`$87,723.65`**
  - **Adjusted Book Balance:** `$87,490.75` - `$127.30` (Bank Fees) - `$480.00` (NSF Return) + `$55.20` (Interest) + `$785.00` (Clerical Errors) = **`$87,723.65`**
  - **Net Variance:** **`$0.00` (Perfect Balance)**
- **🔍 Ambiguity Detection:** Identifies identical disbursement amounts on overlapping dates and flags them for auditor sign-off rather than guessing.
- **📄 Publication-Grade CPA PDF Export:** Dynamically compiles the verified balance proof, adjusting journal entries, and reviewer memo into a vector PDF via ReportLab.
- **📊 Scientific Evaluation Harness:** Benchmarks 3 distinct architectures (**v0 Baseline**, **v1 Structured Skill**, **v2 Full Agent**) across 10 operational edge cases.

---

## 📊 Benchmark Evaluations (v0 vs. v1 vs. v2)

| Metric | v0 (Raw Claude Baseline) | v1 (Structured Skill) | v2 (Full Production Agent) |
| :--- | :---: | :---: | :---: |
| **Pass Rate** | `50.0%` (Failed edge cases) | `100.0%` | **`100.0%`** |
| **False Matches** | `2` (Force-matched wires) | `0` | **`0` (Zero false pairings)** |
| **Hallucinated IDs** | `0` | `0` | **`0`** |
| **Avg Token Cost / Run** | `$0.042` | `$0.051` | **`$0.023` (55% reduction)** |
| **Average Latency** | `1.8s` | `2.0s` | **`2.9s` (Full verification)** |

---

## 📂 Repository Structure

```
recon-draft/
├── app/
│   ├── app.py                     # Flask REST API backend & static file server
│   ├── static/                    # CSS design system (tokens, themes) & client JS
│   └── templates/                 # Jinja2 templates (run, review, evals, hood)
├── data/
│   └── variants/                  # Authentic synthetic scenario datasets
│       ├── clean/                 # Perfect 1-to-1 baseline
│       ├── timing/                # Outstanding checks & deposits in transit
│       ├── fees/                  # Unbooked bank fees, interest, NSF check
│       ├── errors/                # Digit transpositions & duplicate entries
│       ├── tricky/                # Ambiguous identical amount wires
│       └── full/                  # Production scenario (118 transactions)
├── docs/
│   ├── MASTER_PROJECT_GUIDE.md    # Complete master interview & technical guide
│   ├── TIEOUT_RULES.md            # GAAP two-column tie-out specification
│   └── DOMAIN_INTERVIEW.md        # Domain accounting rules & constraints
├── evals/
│   ├── run_evals.py               # Benchmark evaluation execution harness
│   └── edge_cases.py              # Scripted edge cases & failure modes
├── src/
│   ├── matcher.py                 # Deterministic Python pre-matching algorithm
│   ├── money.py                   # Strict integer cents currency formatter
│   ├── pdf_export.py              # ReportLab vector PDF generator
│   ├── runners.py                 # Pipeline execution agents (v0, v1, v2)
│   ├── scoring.py                 # Automated answer key scoring engine
│   ├── tieout.py                  # Deterministic mathematical balance proof
│   ├── tools.py                   # Inspection tools for LLM agent
│   └── verify.py                  # Output guardrails & schema validator
├── tests/                         # Full Pytest test suite (82 tests passing)
├── render.yaml                    # Infrastructure-as-code for Render deployment
└── requirements.txt               # Production Python dependencies
```

---

## 🚀 Quickstart & Local Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Chandrashekhar-cloud/recon-draft.git
cd recon-draft
```

### 2. Set Up Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory:
```bash
ANTHROPIC_API_KEY=your_anthropic_api_key_here
CLAUDE_MODEL=claude-3-5-sonnet-20241022
```
*(Note: You can also run in **Replay Mode** completely offline with zero API keys).*

### 5. Start the Application
```bash
python app/app.py
```
Open your browser at **`http://localhost:5000`**.

---

## 🧪 Running the Test Suite

Recon Draft includes **82 comprehensive unit and integration tests** covering monetary arithmetic, tie-out proofs, LLM parsing, guardrails, and API endpoints:

```bash
pytest
```

---

## ☁️ Deployment

The project is configured for 1-click deployment on **Render** via [`render.yaml`](render.yaml):
- **Runtime:** Python 3.11.9
- **Server:** Gunicorn (`--workers 1 --threads 4 --timeout 120`)
- **CI/CD:** Automated GitHub Actions test pipeline triggers on every push to `main`.
