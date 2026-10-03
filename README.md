# Recon Draft ⚖️
### Autonomous Bank Reconciliation Assistant • Built for Review

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
- **Primary Demo:** [https://recon-draft-s0tm.onrender.com/run](https://recon-draft-s0tm.onrender.com/run) *(Click "▶ Run Recommended Demo")*
- **Architecture Benchmarks:** [https://recon-draft-s0tm.onrender.com/evals](https://recon-draft-s0tm.onrender.com/evals)

---

## 🏛️ System Architecture


