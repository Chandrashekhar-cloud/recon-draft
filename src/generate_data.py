"""Synthetic bank reconciliation test data and answer key generator.

Generates ground-truth datasets for 'Brightloop Inc' (September 2026) across 6 variants:
- clean: only date_lag and normal matches
- timing: outstanding checks and deposits in transit
- fees: bank fees, interest, NSF
- errors: transposition, duplicate, sign error
- tricky: one_to_many, net_of_fee, ambiguous $500 pair
- full: a mix of everything

Follows docs/SCHEMA.md and docs/TIEOUT_RULES.md.
"""

from copy import deepcopy
import csv
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Tuple


VARIANTS = ["clean", "timing", "fees", "errors", "tricky", "full"]

PERIOD_START = "2026-09-01"
PERIOD_END = "2026-09-30"
OPENING_BALANCE_CENTS = 5000000  # $50,000.00 starting balance

SEEDS = {
    "clean": 20260901,
    "timing": 20260902,
    "fees": 20260903,
    "errors": 20260904,
    "tricky": 20260905,
    "full": 20260906,
}


def build_base_events() -> List[Dict[str, Any]]:
    """Build ~50-55 realistic true-world cash events for Brightloop Inc in Sep 2026."""
    events = [
        # Major monthly operating expenses
        {"date": "2026-09-01", "desc": "Soma Office Suites Rent Check #401", "amount_cents": -450000, "type": "check", "ref": "401", "lag_days": 2},
        {"date": "2026-09-05", "desc": "BlueShield Employee Health Plan", "amount_cents": -240000, "type": "ach", "ref": "ACH-HLTH-09", "lag_days": 1},
        {"date": "2026-09-08", "desc": "Comcast Business Fiber Internet", "amount_cents": -35000, "type": "ach", "ref": "COMCAST-882", "lag_days": 1},
        {"date": "2026-09-09", "desc": "Pillsbury Legal Advisory Retainer", "amount_cents": -220000, "type": "ach", "ref": "INV-7712", "lag_days": 2},
        {"date": "2026-09-11", "desc": "GrowthMetrics Marketing Agency", "amount_cents": -350000, "type": "ach", "ref": "ACH-GM-09", "lag_days": 1},
        {"date": "2026-09-12", "desc": "PG&E Electric Utility Service", "amount_cents": -42000, "type": "ach", "ref": "PGE-SEP", "lag_days": 1},
        {"date": "2026-09-15", "desc": "Gusto Payroll Run 1 (1st-15th)", "amount_cents": -1850000, "type": "ach", "ref": "GUSTO-PAY-01", "lag_days": 1},
        {"date": "2026-09-17", "desc": "Contract UI/UX Designer Payment", "amount_cents": -125000, "type": "ach", "ref": "ACH-DESIGN-09", "lag_days": 2},
        {"date": "2026-09-21", "desc": "BDO Accounting & Tax Retainer", "amount_cents": -150000, "type": "ach", "ref": "ACH-BDO-09", "lag_days": 1},
        {"date": "2026-09-23", "desc": "Sparkle Office Cleaning Check #402", "amount_cents": -40000, "type": "check", "ref": "402", "lag_days": 2},
        {"date": "2026-09-30", "desc": "Gusto Payroll Run 2 (16th-30th)", "amount_cents": -1850000, "type": "ach", "ref": "GUSTO-PAY-02", "lag_days": 0},

        # Software subscriptions & cloud infra
        {"date": "2026-09-03", "desc": "Amazon Web Services Cloud Hosting", "amount_cents": -184050, "type": "card", "ref": "AWS-SEP26", "lag_days": 0},
        {"date": "2026-09-04", "desc": "Google Workspace Enterprise Email", "amount_cents": -24000, "type": "card", "ref": "GSUITE-09", "lag_days": 0},
        {"date": "2026-09-06", "desc": "Slack Technologies Subscription", "amount_cents": -18000, "type": "card", "ref": "SLACK-09", "lag_days": 0},
        {"date": "2026-09-07", "desc": "GitHub Team Subscription", "amount_cents": -8400, "type": "card", "ref": "GH-SEP", "lag_days": 0},
        {"date": "2026-09-10", "desc": "Datadog Cloud Monitoring", "amount_cents": -65000, "type": "card", "ref": "DDOG-09", "lag_days": 0},
        {"date": "2026-09-13", "desc": "Apple Store Developer MacBooks", "amount_cents": -289900, "type": "card", "ref": "APL-3329", "lag_days": 0},
        {"date": "2026-09-14", "desc": "HubSpot Marketing Hub", "amount_cents": -89000, "type": "card", "ref": "HUBSPOT-09", "lag_days": 0},
        {"date": "2026-09-16", "desc": "Figma Enterprise License", "amount_cents": -12000, "type": "card", "ref": "FIGMA-09", "lag_days": 0},
        {"date": "2026-09-18", "desc": "Chipotle Executive Team Catering", "amount_cents": -27550, "type": "card", "ref": "CHP-883", "lag_days": 0},
        {"date": "2026-09-19", "desc": "Zoom Video Communications", "amount_cents": -7500, "type": "card", "ref": "ZOOM-09", "lag_days": 0},
        {"date": "2026-09-20", "desc": "United Airlines SaaS Conference Flight", "amount_cents": -58000, "type": "card", "ref": "UA-993", "lag_days": 0},
        {"date": "2026-09-21", "desc": "Hyatt Regency Conference Hotel", "amount_cents": -41000, "type": "card", "ref": "HYATT-74", "lag_days": 0},
        {"date": "2026-09-22", "desc": "OpenAI API Usage Billing", "amount_cents": -43025, "type": "card", "ref": "OPENAI-09", "lag_days": 0},
        {"date": "2026-09-25", "desc": "Notion Labs Team Workspace", "amount_cents": -15000, "type": "card", "ref": "NOTION-09", "lag_days": 0},

        # Enterprise Customer Payments (Direct Wire / ACH)
        {"date": "2026-09-04", "desc": "Acme Corp Annual SaaS License", "amount_cents": 1200000, "type": "ach", "ref": "INV-801", "lag_days": 1},
        {"date": "2026-09-10", "desc": "TechFlow Systems Enterprise Retainer", "amount_cents": 850000, "type": "ach", "ref": "INV-802", "lag_days": 1},
        {"date": "2026-09-18", "desc": "Apex Global Multi-Seat Subscription", "amount_cents": 1500000, "type": "ach", "ref": "INV-803", "lag_days": 2},
        {"date": "2026-09-24", "desc": "Nexus Security Enterprise Deployment", "amount_cents": 620000, "type": "ach", "ref": "INV-804", "lag_days": 1},
        {"date": "2026-09-27", "desc": "Quantum Dynamics Annual Contract", "amount_cents": 940000, "type": "ach", "ref": "INV-805", "lag_days": 1},

        # Daily / Bi-daily Stripe Subscription Revenue Payouts
        {"date": "2026-09-02", "desc": "Stripe Payout Daily Batch", "amount_cents": 142000, "type": "deposit", "ref": "STRIPE-0902", "lag_days": 1},
        {"date": "2026-09-03", "desc": "Stripe Payout Daily Batch", "amount_cents": 89000, "type": "deposit", "ref": "STRIPE-0903", "lag_days": 1},
        {"date": "2026-09-05", "desc": "Stripe Payout Daily Batch", "amount_cents": 215000, "type": "deposit", "ref": "STRIPE-0905", "lag_days": 1},
        {"date": "2026-09-06", "desc": "Stripe Payout Daily Batch", "amount_cents": 175000, "type": "deposit", "ref": "STRIPE-0906", "lag_days": 1},
        {"date": "2026-09-08", "desc": "Stripe Payout Daily Batch", "amount_cents": 98000, "type": "deposit", "ref": "STRIPE-0908", "lag_days": 1},
        {"date": "2026-09-09", "desc": "Stripe Payout Daily Batch", "amount_cents": 320000, "type": "deposit", "ref": "STRIPE-0909", "lag_days": 1},
        {"date": "2026-09-11", "desc": "Stripe Payout Daily Batch", "amount_cents": 164000, "type": "deposit", "ref": "STRIPE-0911", "lag_days": 1},
        {"date": "2026-09-12", "desc": "Stripe Payout Daily Batch", "amount_cents": 280000, "type": "deposit", "ref": "STRIPE-0912", "lag_days": 1},
        {"date": "2026-09-14", "desc": "Stripe Payout Daily Batch", "amount_cents": 110000, "type": "deposit", "ref": "STRIPE-0914", "lag_days": 1},
        {"date": "2026-09-16", "desc": "Stripe Payout Daily Batch", "amount_cents": 450000, "type": "deposit", "ref": "STRIPE-0916", "lag_days": 1},
        {"date": "2026-09-17", "desc": "Stripe Payout Daily Batch", "amount_cents": 185000, "type": "deposit", "ref": "STRIPE-0917", "lag_days": 1},
        {"date": "2026-09-19", "desc": "Stripe Payout Daily Batch", "amount_cents": 230000, "type": "deposit", "ref": "STRIPE-0919", "lag_days": 1},
        {"date": "2026-09-20", "desc": "Stripe Payout Daily Batch", "amount_cents": 145000, "type": "deposit", "ref": "STRIPE-0920", "lag_days": 1},
        {"date": "2026-09-22", "desc": "Stripe Payout Daily Batch", "amount_cents": 310000, "type": "deposit", "ref": "STRIPE-0922", "lag_days": 1},
        {"date": "2026-09-23", "desc": "Stripe Payout Daily Batch", "amount_cents": 205000, "type": "deposit", "ref": "STRIPE-0923", "lag_days": 1},
        {"date": "2026-09-25", "desc": "Stripe Payout Daily Batch", "amount_cents": 192000, "type": "deposit", "ref": "STRIPE-0925", "lag_days": 1},
        {"date": "2026-09-26", "desc": "Stripe Payout Daily Batch", "amount_cents": 275000, "type": "deposit", "ref": "STRIPE-0926", "lag_days": 1},
        {"date": "2026-09-28", "desc": "Stripe Payout Daily Batch", "amount_cents": 340000, "type": "deposit", "ref": "STRIPE-0928", "lag_days": 1},
        {"date": "2026-09-29", "desc": "Stripe Payout Daily Batch", "amount_cents": 220000, "type": "deposit", "ref": "STRIPE-0929", "lag_days": 1},
    ]
    return events


def add_days_iso(date_str: str, days: int) -> str:
    """Helper to add calendar days to a YYYY-MM-DD date within September 2026."""
    year, month, day = map(int, date_str.split("-"))
    new_day = min(30, max(1, day + days))
    return f"{year:04d}-{month:02d}-{new_day:02d}"


def build_variant(variant_name: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str, Dict[str, Any]]:
    """Build bank records, ledger records, notes, and answer key for a specific variant."""
    seed = SEEDS[variant_name]
    random.seed(seed)

    base_events = build_base_events()

    bank_rows: List[Dict[str, Any]] = []
    ledger_rows: List[Dict[str, Any]] = []
    matches: List[Dict[str, Any]] = []
    reconciling_items: List[Dict[str, Any]] = []
    ambiguous_groups: List[Dict[str, Any]] = []

    bank_id_counter = 1001
    ledger_id_counter = 2001

    def next_bank_id() -> str:
        nonlocal bank_id_counter
        bid = f"BNK-{bank_id_counter}"
        bank_id_counter += 1
        return bid

    def next_ledger_id() -> str:
        nonlocal ledger_id_counter
        lid = f"GL-{ledger_id_counter}"
        ledger_id_counter += 1
        return lid

    # Populate standard matched transactions from base events
    for ev in base_events:
        bid = next_bank_id()
        lid = next_ledger_id()

        ledger_date = ev["date"]
        lag = ev.get("lag_days", 0)
        bank_date = add_days_iso(ledger_date, lag)

        bank_rows.append({
            "bank_id": bid,
            "date": bank_date,
            "description": ev["desc"].upper(),
            "amount_cents": ev["amount_cents"],
        })

        ledger_rows.append({
            "ledger_id": lid,
            "date": ledger_date,
            "memo": ev["desc"],
            "amount_cents": ev["amount_cents"],
            "reference": ev["ref"],
            "type": ev["type"],
        })

        matches.append({
            "bank_ids": [bid],
            "ledger_ids": [lid],
            "kind": "date_lag" if lag > 0 else "exact",
        })

    # Plant specific traps according to the variant specification
    notes = ""

    if variant_name == "clean":
        notes = (
            "Brightloop Inc - September 2026 Reconciliation Notes.\n"
            "All transactions cleared normally with standard 1-2 business day settlement timing.\n"
            "No unrecorded fees, check timing issues, or manual errors reported."
        )

    elif variant_name == "timing":
        # Outstanding check 1 (in ledger, not in bank)
        lid_chk1 = next_ledger_id()
        ledger_rows.append({
            "ledger_id": lid_chk1,
            "date": "2026-09-28",
            "memo": "Apex Office Supplies Check #403",
            "amount_cents": -68000,
            "reference": "403",
            "type": "check",
        })
        reconciling_items.append({
            "item_id": lid_chk1,
            "side": "ledger",
            "category": "outstanding_check",
            "amount_cents": -68000,
            "needs_journal_entry": False,
        })

        # Outstanding check 2 (in ledger, not in bank)
        lid_chk2 = next_ledger_id()
        ledger_rows.append({
            "ledger_id": lid_chk2,
            "date": "2026-09-29",
            "memo": "San Francisco Courier Services Check #404",
            "amount_cents": -45000,
            "reference": "404",
            "type": "check",
        })
        reconciling_items.append({
            "item_id": lid_chk2,
            "side": "ledger",
            "category": "outstanding_check",
            "amount_cents": -45000,
            "needs_journal_entry": False,
        })

        # Deposit in transit (in ledger, not in bank)
        lid_dep = next_ledger_id()
        ledger_rows.append({
            "ledger_id": lid_dep,
            "date": "2026-09-30",
            "memo": "Client Deposit Summit Health Check #8812",
            "amount_cents": 320000,
            "reference": "DEP-SEP30",
            "type": "deposit",
        })
        reconciling_items.append({
            "item_id": lid_dep,
            "side": "ledger",
            "category": "deposit_in_transit",
            "amount_cents": 320000,
            "needs_journal_entry": False,
        })

        notes = (
            "Brightloop Inc - September 2026 Reconciliation Notes.\n"
            "Checks #403 and #404 were mailed to vendors near month-end and have not yet cleared the bank.\n"
            "A client check deposit from Summit Health was logged into the general ledger on September 30 "
            "after bank cutoff hours."
        )

    elif variant_name == "fees":
        # Unbooked bank service fee (in bank, not in ledger)
        bid_fee = next_bank_id()
        bank_rows.append({
            "bank_id": bid_fee,
            "date": "2026-09-30",
            "description": "MONTHLY COMMERCIAL ACCOUNT MAINTENANCE FEE",
            "amount_cents": -3500,
        })
        reconciling_items.append({
            "item_id": bid_fee,
            "side": "bank",
            "category": "bank_fee_unbooked",
            "amount_cents": -3500,
            "needs_journal_entry": True,
        })

        # Unbooked earned interest (in bank, not in ledger)
        bid_int = next_bank_id()
        bank_rows.append({
            "bank_id": bid_int,
            "date": "2026-09-30",
            "description": "INTEREST EARNED ON CHECKING BALANCE",
            "amount_cents": 6845,
        })
        reconciling_items.append({
            "item_id": bid_int,
            "side": "bank",
            "category": "interest_unbooked",
            "amount_cents": 6845,
            "needs_journal_entry": True,
        })

        # NSF return (in bank, not in ledger)
        bid_nsf = next_bank_id()
        bank_rows.append({
            "bank_id": bid_nsf,
            "date": "2026-09-25",
            "description": "RETURNED ITEM NSF CHECK #1092 HORIZON LLC",
            "amount_cents": -52000,
        })
        reconciling_items.append({
            "item_id": bid_nsf,
            "side": "bank",
            "category": "nsf_return",
            "amount_cents": -52000,
            "needs_journal_entry": True,
        })

        notes = (
            "Brightloop Inc - September 2026 Reconciliation Notes.\n"
            "The bank assessed a monthly maintenance fee on Sep 30 and credited earned interest.\n"
            "A customer check from Horizon LLC previously deposited bounced and was deducted as an NSF return on Sep 25."
        )

    elif variant_name == "errors":
        # Transposition error: Bank is correct $1,450.00 (-145000); Ledger booked $1,540.00 (-154000)
        # Difference: Ledger cash is understated by $90.00 (9000 cents)
        bid_trans = next_bank_id()
        lid_trans = next_ledger_id()
        bank_rows.append({
            "bank_id": bid_trans,
            "date": "2026-09-14",
            "description": "OFFICE SUPPLIES DEPOT",
            "amount_cents": -145000,
        })
        ledger_rows.append({
            "ledger_id": lid_trans,
            "date": "2026-09-14",
            "memo": "Office Supplies Depot",
            "amount_cents": -154000,
            "reference": "INV-1450",
            "type": "card",
        })
        matches.append({
            "bank_ids": [bid_trans],
            "ledger_ids": [lid_trans],
            "kind": "exact",
        })
        reconciling_items.append({
            "item_id": lid_trans,
            "side": "ledger",
            "category": "transposition_error",
            "amount_cents": 9000,  # +$90.00 correction to books
            "needs_journal_entry": True,
        })

        # Duplicate ledger entry: Subscription for Figma booked twice in ledger, bank debited once
        # Difference: Ledger cash is understated by $120.00 (12000 cents)
        lid_dup = next_ledger_id()
        ledger_rows.append({
            "ledger_id": lid_dup,
            "date": "2026-09-16",
            "memo": "Figma Enterprise License - Duplicate Entry",
            "amount_cents": -12000,
            "reference": "FIGMA-09-DUP",
            "type": "card",
        })
        reconciling_items.append({
            "item_id": lid_dup,
            "side": "ledger",
            "category": "duplicate_ledger",
            "amount_cents": 12000,  # +$120.00 correction to books
            "needs_journal_entry": True,
        })

        # Sign error: Vendor rebate/refund of $250.00 (+25000 cents) entered in ledger as expense -$250.00 (-25000 cents)
        # Difference: Ledger cash is understated by $500.00 (50000 cents)
        bid_sign = next_bank_id()
        lid_sign = next_ledger_id()
        bank_rows.append({
            "bank_id": bid_sign,
            "date": "2026-09-22",
            "description": "DATADOG ANNUAL REBATE REFUND",
            "amount_cents": 25000,
        })
        ledger_rows.append({
            "ledger_id": lid_sign,
            "date": "2026-09-22",
            "memo": "Datadog Rebate Erroneous Expense Entry",
            "amount_cents": -25000,
            "reference": "REB-991",
            "type": "card",
        })
        matches.append({
            "bank_ids": [bid_sign],
            "ledger_ids": [lid_sign],
            "kind": "exact",
        })
        reconciling_items.append({
            "item_id": lid_sign,
            "side": "ledger",
            "category": "sign_error",
            "amount_cents": 50000,  # +$500.00 correction to books (+25000 - (-25000))
            "needs_journal_entry": True,
        })

        notes = (
            "Brightloop Inc - September 2026 Reconciliation Notes.\n"
            "An invoice on Sep 14 was recorded with transposed digits ($1,540.00 vs $1,450.00 actual).\n"
            "A duplicate entry was accidentally posted for the monthly Figma subscription.\n"
            "A vendor rebate received on Sep 22 was mistakenly entered as an expense rather than a cash receipt."
        )

    elif variant_name == "tricky":
        # One-to-many: One bank deposit of $4,850.00 equals 3 ledger invoices ($1,200.00 + $2,150.00 + $1,500.00)
        bid_batch = next_bank_id()
        lid_inv1 = next_ledger_id()
        lid_inv2 = next_ledger_id()
        lid_inv3 = next_ledger_id()

        bank_rows.append({
            "bank_id": bid_batch,
            "date": "2026-09-15",
            "description": "MERCHANT SETTLEMENT BATCH DEP",
            "amount_cents": 485000,
        })
        ledger_rows.append({
            "ledger_id": lid_inv1,
            "date": "2026-09-15",
            "memo": "Client Settlement Invoice #1041",
            "amount_cents": 120000,
            "reference": "INV-1041",
            "type": "deposit",
        })
        ledger_rows.append({
            "ledger_id": lid_inv2,
            "date": "2026-09-15",
            "memo": "Client Settlement Invoice #1042",
            "amount_cents": 215000,
            "reference": "INV-1042",
            "type": "deposit",
        })
        ledger_rows.append({
            "ledger_id": lid_inv3,
            "date": "2026-09-15",
            "memo": "Client Settlement Invoice #1043",
            "amount_cents": 150000,
            "reference": "INV-1043",
            "type": "deposit",
        })
        matches.append({
            "bank_ids": [bid_batch],
            "ledger_ids": [lid_inv1, lid_inv2, lid_inv3],
            "kind": "one_to_many",
        })

        # Net of fee: Ledger sale $3,000.00; Stripe fee $87.30 (8730 cents); Bank payout $2,912.70 (291270 cents)
        bid_net = next_bank_id()
        lid_net = next_ledger_id()
        bank_rows.append({
            "bank_id": bid_net,
            "date": "2026-09-19",
            "description": "STRIPE PAYOUT NET OF FEE",
            "amount_cents": 291270,
        })
        ledger_rows.append({
            "ledger_id": lid_net,
            "date": "2026-09-19",
            "memo": "Enterprise Onboarding Gross Sale",
            "amount_cents": 300000,
            "reference": "STRIPE-NET-0919",
            "type": "deposit",
        })
        matches.append({
            "bank_ids": [bid_net],
            "ledger_ids": [lid_net],
            "kind": "net_of_fee",
        })
        reconciling_items.append({
            "item_id": bid_net,
            "side": "bank",
            "category": "bank_fee_unbooked",
            "amount_cents": -8730,  # Unbooked Stripe fee needing journal entry
            "needs_journal_entry": True,
        })

        # Ambiguous pair: Two identical $500.00 payments on Sep 18 with indistinct bank descriptions
        bid_amb1 = next_bank_id()
        bid_amb2 = next_bank_id()
        lid_amb1 = next_ledger_id()
        lid_amb2 = next_ledger_id()

        bank_rows.append({
            "bank_id": bid_amb1,
            "date": "2026-09-18",
            "description": "OUTGOING WIRE TRANSFER 500",
            "amount_cents": -50000,
        })
        bank_rows.append({
            "bank_id": bid_amb2,
            "date": "2026-09-18",
            "description": "OUTGOING WIRE TRANSFER 500",
            "amount_cents": -50000,
        })
        ledger_rows.append({
            "ledger_id": lid_amb1,
            "date": "2026-09-18",
            "memo": "Contract Specialist Alpha Payment",
            "amount_cents": -50000,
            "reference": "WIRE-500A",
            "type": "transfer",
        })
        ledger_rows.append({
            "ledger_id": lid_amb2,
            "date": "2026-09-18",
            "memo": "Contract Specialist Beta Payment",
            "amount_cents": -50000,
            "reference": "WIRE-500B",
            "type": "transfer",
        })
        matches.append({
            "bank_ids": [bid_amb1],
            "ledger_ids": [lid_amb1],
            "kind": "exact",
        })
        matches.append({
            "bank_ids": [bid_amb2],
            "ledger_ids": [lid_amb2],
            "kind": "exact",
        })
        ambiguous_groups.append({
            "bank_ids": [bid_amb1, bid_amb2],
            "ledger_ids": [lid_amb1, lid_amb2],
            "reason": "Two identical $500.00 payments on the same date with indistinguishable wire memos.",
        })

        notes = (
            "Brightloop Inc - September 2026 Reconciliation Notes.\n"
            "Stripe payouts arrive net of processing fees.\n"
            "Merchant settlements batch multiple customer invoices into a single deposit.\n"
            "Two identical wire transfers of $500.00 were executed on Sep 18 for external contractors."
        )

    elif variant_name == "full":
        # 1. Outstanding check (in ledger, not in bank)
        lid_chk = next_ledger_id()
        ledger_rows.append({
            "ledger_id": lid_chk,
            "date": "2026-09-28",
            "memo": "Legal Defense Retainer Check #405",
            "amount_cents": -65000,
            "reference": "405",
            "type": "check",
        })
        reconciling_items.append({
            "item_id": lid_chk,
            "side": "ledger",
            "category": "outstanding_check",
            "amount_cents": -65000,
            "needs_journal_entry": False,
        })

        # 2. Deposit in transit (in ledger, not in bank)
        lid_dep = next_ledger_id()
        ledger_rows.append({
            "ledger_id": lid_dep,
            "date": "2026-09-30",
            "memo": "Enterprise Customer Check Deposit Vertex Corp",
            "amount_cents": 280000,
            "reference": "DEP-SEP30B",
            "type": "deposit",
        })
        reconciling_items.append({
            "item_id": lid_dep,
            "side": "ledger",
            "category": "deposit_in_transit",
            "amount_cents": 280000,
            "needs_journal_entry": False,
        })

        # 3. Unbooked bank fee
        bid_fee = next_bank_id()
        bank_rows.append({
            "bank_id": bid_fee,
            "date": "2026-09-30",
            "description": "MONTHLY COMMERCIAL SERVICE CHARGE",
            "amount_cents": -4000,
        })
        reconciling_items.append({
            "item_id": bid_fee,
            "side": "bank",
            "category": "bank_fee_unbooked",
            "amount_cents": -4000,
            "needs_journal_entry": True,
        })

        # 4. Unbooked earned interest
        bid_int = next_bank_id()
        bank_rows.append({
            "bank_id": bid_int,
            "date": "2026-09-30",
            "description": "INTEREST CREDIT CHECKING ACCOUNT",
            "amount_cents": 5520,
        })
        reconciling_items.append({
            "item_id": bid_int,
            "side": "bank",
            "category": "interest_unbooked",
            "amount_cents": 5520,
            "needs_journal_entry": True,
        })

        # 5. NSF return
        bid_nsf = next_bank_id()
        bank_rows.append({
            "bank_id": bid_nsf,
            "date": "2026-09-24",
            "description": "RETURNED ITEM NSF CHECK #902 PACIFIC LABS",
            "amount_cents": -48000,
        })
        reconciling_items.append({
            "item_id": bid_nsf,
            "side": "bank",
            "category": "nsf_return",
            "amount_cents": -48000,
            "needs_journal_entry": True,
        })

        # 6. Duplicate ledger entry
        lid_dup = next_ledger_id()
        ledger_rows.append({
            "ledger_id": lid_dup,
            "date": "2026-09-17",
            "memo": "Duplicate Posting Server Backup Hosting",
            "amount_cents": -9500,
            "reference": "BKP-09-DUP",
            "type": "card",
        })
        reconciling_items.append({
            "item_id": lid_dup,
            "side": "ledger",
            "category": "duplicate_ledger",
            "amount_cents": 9500,
            "needs_journal_entry": True,
        })

        # 7. Transposition error: Bank $1,230.00 (-123000), Ledger recorded $1,320.00 (-132000)
        bid_trans = next_bank_id()
        lid_trans = next_ledger_id()
        bank_rows.append({
            "bank_id": bid_trans,
            "date": "2026-09-13",
            "description": "HARDWARE REPAIR SERVICES",
            "amount_cents": -123000,
        })
        ledger_rows.append({
            "ledger_id": lid_trans,
            "date": "2026-09-13",
            "memo": "Hardware Repair Services",
            "amount_cents": -132000,
            "reference": "REP-882",
            "type": "card",
        })
        matches.append({
            "bank_ids": [bid_trans],
            "ledger_ids": [lid_trans],
            "kind": "exact",
        })
        reconciling_items.append({
            "item_id": lid_trans,
            "side": "ledger",
            "category": "transposition_error",
            "amount_cents": 9000,  # +$90.00 adjustment to book
            "needs_journal_entry": True,
        })

        # 8. Sign error: Vendor rebate +$300.00 (+30000) recorded as expense -$300.00 (-30000)
        bid_sign = next_bank_id()
        lid_sign = next_ledger_id()
        bank_rows.append({
            "bank_id": bid_sign,
            "date": "2026-09-22",
            "description": "VENDOR PROMO REBATE CREDIT",
            "amount_cents": 30000,
        })
        ledger_rows.append({
            "ledger_id": lid_sign,
            "date": "2026-09-22",
            "memo": "Vendor Promo Rebate Recorded As Expense",
            "amount_cents": -30000,
            "reference": "PROMO-300",
            "type": "card",
        })
        matches.append({
            "bank_ids": [bid_sign],
            "ledger_ids": [lid_sign],
            "kind": "exact",
        })
        reconciling_items.append({
            "item_id": lid_sign,
            "side": "ledger",
            "category": "sign_error",
            "amount_cents": 60000,  # +$600.00 adjustment to book
            "needs_journal_entry": True,
        })

        # 9. One-to-many match
        bid_batch = next_bank_id()
        lid_b1 = next_ledger_id()
        lid_b2 = next_ledger_id()
        lid_b3 = next_ledger_id()
        bank_rows.append({
            "bank_id": bid_batch,
            "date": "2026-09-15",
            "description": "MERCHANT SETTLEMENT BATCH DEP",
            "amount_cents": 485000,
        })
        ledger_rows.append({
            "ledger_id": lid_b1,
            "date": "2026-09-15",
            "memo": "Client Settlement Invoice #1041",
            "amount_cents": 120000,
            "reference": "INV-1041",
            "type": "deposit",
        })
        ledger_rows.append({
            "ledger_id": lid_b2,
            "date": "2026-09-15",
            "memo": "Client Settlement Invoice #1042",
            "amount_cents": 215000,
            "reference": "INV-1042",
            "type": "deposit",
        })
        ledger_rows.append({
            "ledger_id": lid_b3,
            "date": "2026-09-15",
            "memo": "Client Settlement Invoice #1043",
            "amount_cents": 150000,
            "reference": "INV-1043",
            "type": "deposit",
        })
        matches.append({
            "bank_ids": [bid_batch],
            "ledger_ids": [lid_b1, lid_b2, lid_b3],
            "kind": "one_to_many",
        })

        # 10. Net of fee
        bid_net = next_bank_id()
        lid_net = next_ledger_id()
        bank_rows.append({
            "bank_id": bid_net,
            "date": "2026-09-19",
            "description": "STRIPE PAYOUT NET OF FEE",
            "amount_cents": 291270,
        })
        ledger_rows.append({
            "ledger_id": lid_net,
            "date": "2026-09-19",
            "memo": "Enterprise Onboarding Gross Sale",
            "amount_cents": 300000,
            "reference": "STRIPE-NET-0919",
            "type": "deposit",
        })
        matches.append({
            "bank_ids": [bid_net],
            "ledger_ids": [lid_net],
            "kind": "net_of_fee",
        })
        reconciling_items.append({
            "item_id": bid_net,
            "side": "bank",
            "category": "bank_fee_unbooked",
            "amount_cents": -8730,
            "needs_journal_entry": True,
        })

        # 11. Ambiguous pair
        bid_a1 = next_bank_id()
        bid_a2 = next_bank_id()
        lid_a1 = next_ledger_id()
        lid_a2 = next_ledger_id()
        bank_rows.append({
            "bank_id": bid_a1,
            "date": "2026-09-18",
            "description": "OUTGOING WIRE TRANSFER 500",
            "amount_cents": -50000,
        })
        bank_rows.append({
            "bank_id": bid_a2,
            "date": "2026-09-18",
            "description": "OUTGOING WIRE TRANSFER 500",
            "amount_cents": -50000,
        })
        ledger_rows.append({
            "ledger_id": lid_a1,
            "date": "2026-09-18",
            "memo": "Contract Specialist Alpha Payment",
            "amount_cents": -50000,
            "reference": "WIRE-500A",
            "type": "transfer",
        })
        ledger_rows.append({
            "ledger_id": lid_a2,
            "date": "2026-09-18",
            "memo": "Contract Specialist Beta Payment",
            "amount_cents": -50000,
            "reference": "WIRE-500B",
            "type": "transfer",
        })
        matches.append({
            "bank_ids": [bid_a1],
            "ledger_ids": [lid_a1],
            "kind": "exact",
        })
        matches.append({
            "bank_ids": [bid_a2],
            "ledger_ids": [lid_a2],
            "kind": "exact",
        })
        ambiguous_groups.append({
            "bank_ids": [bid_a1, bid_a2],
            "ledger_ids": [lid_a1, lid_a2],
            "reason": "Two identical $500.00 payments on the same date with indistinguishable wire memos.",
        })

        notes = (
            "Brightloop Inc - September 2026 Full Variant Reconciliation Notes.\n"
            "Stripe payouts arrive net of processing fees.\n"
            "Multiple checks were mailed near month-end and a customer deposit was made after banking hours on Sep 30.\n"
            "Monthly bank service fee and earned interest post on the final business day.\n"
            "A customer check was returned unpaid (NSF).\n"
            "Clerical anomalies include transposed digits on repair services, duplicate backup posting, and an inverted rebate sign."
        )

    # Sort bank rows by date, then bank_id
    bank_rows.sort(key=lambda r: (r["date"], r["bank_id"]))

    # Calculate running balance for bank
    curr_balance = OPENING_BALANCE_CENTS
    for row in bank_rows:
        curr_balance += row["amount_cents"]
        row["running_balance_cents"] = curr_balance

    bank_closing_cents = curr_balance

    # Sort ledger rows by date, then ledger_id
    ledger_rows.sort(key=lambda r: (r["date"], r["ledger_id"]))

    # Calculate book closing
    book_closing_cents = OPENING_BALANCE_CENTS + sum(r["amount_cents"] for r in ledger_rows)

    # Calculate adjusted bank and adjusted book from answer key rules
    deposits_in_transit = sum(abs(item["amount_cents"]) for item in reconciling_items if item["category"] == "deposit_in_transit")
    outstanding_checks = sum(abs(item["amount_cents"]) for item in reconciling_items if item["category"] == "outstanding_check")
    unbooked_fees = sum(abs(item["amount_cents"]) for item in reconciling_items if item["category"] == "bank_fee_unbooked")
    nsf_returns = sum(abs(item["amount_cents"]) for item in reconciling_items if item["category"] == "nsf_return")
    unbooked_interest = sum(abs(item["amount_cents"]) for item in reconciling_items if item["category"] == "interest_unbooked")
    book_errors = sum(item["amount_cents"] for item in reconciling_items if item["category"] in ("transposition_error", "duplicate_ledger", "sign_error"))

    adjusted_bank = bank_closing_cents + deposits_in_transit - outstanding_checks
    adjusted_book = book_closing_cents - unbooked_fees - nsf_returns + unbooked_interest + book_errors

    answer_key = {
        "variant": variant_name,
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "balances": {
            "bank_opening_cents": OPENING_BALANCE_CENTS,
            "bank_closing_cents": bank_closing_cents,
            "book_opening_cents": OPENING_BALANCE_CENTS,
            "book_closing_cents": book_closing_cents,
        },
        "matches": matches,
        "reconciling_items": reconciling_items,
        "ambiguous_groups": ambiguous_groups,
        "tie_out": {
            "adjusted_bank_cents": adjusted_bank,
            "adjusted_book_cents": adjusted_book,
            "difference_cents": adjusted_bank - adjusted_book,
        },
    }

    return bank_rows, ledger_rows, notes, answer_key


def verify_tie_out(answer_key: Dict[str, Any]) -> None:
    """Verify adjusted_bank == adjusted_book using the formula in docs/TIEOUT_RULES.md.

    Builds the tie-out calculation purely from the answer key.
    Raises AssertionError if the tie-out condition fails.
    """
    balances = answer_key["balances"]
    bank_closing = balances["bank_closing_cents"]
    book_closing = balances["book_closing_cents"]

    deposits_in_transit = 0
    outstanding_checks = 0
    bank_errors = 0

    unbooked_fees = 0
    nsf_returns = 0
    unbooked_interest = 0
    book_errors = 0

    for item in answer_key["reconciling_items"]:
        cat = item["category"]
        amt = item["amount_cents"]
        side = item["side"]

        if side == "ledger" and cat == "deposit_in_transit":
            deposits_in_transit += abs(amt)
        elif side == "ledger" and cat == "outstanding_check":
            outstanding_checks += abs(amt)
        elif side == "bank" and cat == "bank_fee_unbooked":
            unbooked_fees += abs(amt)
        elif side == "bank" and cat == "nsf_return":
            nsf_returns += abs(amt)
        elif side == "bank" and cat == "interest_unbooked":
            unbooked_interest += abs(amt)
        elif side == "ledger" and cat in ("transposition_error", "duplicate_ledger", "sign_error"):
            book_errors += amt
        elif side == "bank" and cat == "bank_error":
            bank_errors += amt
        else:
            raise ValueError(f"Unknown reconciling item category: {cat} on side {side}")

    calculated_adjusted_bank = bank_closing + deposits_in_transit - outstanding_checks + bank_errors
    calculated_adjusted_book = book_closing - unbooked_fees - nsf_returns + unbooked_interest + book_errors

    expected_bank = answer_key["tie_out"]["adjusted_bank_cents"]
    expected_book = answer_key["tie_out"]["adjusted_book_cents"]
    diff = calculated_adjusted_bank - calculated_adjusted_book

    if calculated_adjusted_bank != expected_bank:
        raise AssertionError(
            f"Calculated adjusted bank ({calculated_adjusted_bank}) != answer key ({expected_bank})"
        )

    if calculated_adjusted_book != expected_book:
        raise AssertionError(
            f"Calculated adjusted book ({calculated_adjusted_book}) != answer key ({expected_book})"
        )

    if diff != 0:
        raise AssertionError(
            f"Tie-out validation failed for variant '{answer_key['variant']}': "
            f"adjusted_bank ({calculated_adjusted_bank}) != adjusted_book ({calculated_adjusted_book}), "
            f"diff = {diff} cents."
        )


def write_variant_data(
    base_dir: Path,
    variant_name: str,
    bank_rows: List[Dict[str, Any]],
    ledger_rows: List[Dict[str, Any]],
    notes: str,
    answer_key: Dict[str, Any],
) -> None:
    """Write bank.csv, ledger.csv, notes.txt, and answer_key.json into data/variants/<name>/."""
    variant_dir = base_dir / "data" / "variants" / variant_name
    variant_dir.mkdir(parents=True, exist_ok=True)

    # 1. bank.csv
    bank_csv_path = variant_dir / "bank.csv"
    with open(bank_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["bank_id", "date", "description", "amount_cents", "running_balance_cents"],
        )
        writer.writeheader()
        writer.writerows(bank_rows)

    # 2. ledger.csv
    ledger_csv_path = variant_dir / "ledger.csv"
    with open(ledger_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["ledger_id", "date", "memo", "amount_cents", "reference", "type"],
        )
        writer.writeheader()
        writer.writerows(ledger_rows)

    # 3. notes.txt
    notes_path = variant_dir / "notes.txt"
    with open(notes_path, "w", encoding="utf-8") as f:
        f.write(notes + "\n")

    # 4. answer_key.json
    answer_key_path = variant_dir / "answer_key.json"
    with open(answer_key_path, "w", encoding="utf-8") as f:
        json.dump(answer_key, f, indent=2)


def main() -> None:
    """Generate all variants, verify tie-outs, save files, and print a summary table."""
    base_dir = Path(__file__).resolve().parent.parent

    print(f"Generating synthetic reconciliation datasets for Brightloop Inc (Sep 2026)...")
    print(f"Target directory: {base_dir / 'data' / 'variants'}\n")

    summary_rows = []

    for variant_name in VARIANTS:
        bank_rows, ledger_rows, notes, answer_key = build_variant(variant_name)

        # IMPORTANT: Run assertion that adjusted_bank == adjusted_book using TIEOUT_RULES.md
        verify_tie_out(answer_key)

        # Write files
        write_variant_data(base_dir, variant_name, bank_rows, ledger_rows, notes, answer_key)

        num_traps = len(answer_key["reconciling_items"]) + len(answer_key["ambiguous_groups"])
        tie_out_ok = answer_key["tie_out"]["difference_cents"] == 0

        summary_rows.append({
            "variant": variant_name,
            "bank_rows": len(bank_rows),
            "ledger_rows": len(ledger_rows),
            "matches": len(answer_key["matches"]),
            "reconciling_items": len(answer_key["reconciling_items"]),
            "ambiguous": len(answer_key["ambiguous_groups"]),
            "total_traps": num_traps,
            "tie_out_ok": "OK" if tie_out_ok else "FAIL",
        })

    # Print summary table
    header = (
        f"{'Variant':<12} | {'Bank Rows':<10} | {'Ledger Rows':<12} | {'Matches':<8} | "
        f"{'Recon Items':<12} | {'Ambiguous':<10} | {'Total Traps':<12} | {'Tie-Out':<8}"
    )
    separator = "-" * len(header)

    print(separator)
    print(header)
    print(separator)

    for row in summary_rows:
        print(
            f"{row['variant']:<12} | {row['bank_rows']:<10} | {row['ledger_rows']:<12} | "
            f"{row['matches']:<8} | {row['reconciling_items']:<12} | {row['ambiguous']:<10} | "
            f"{row['total_traps']:<12} | {row['tie_out_ok']:<8}"
        )

    print(separator)
    print(f"\nAll 6 variants generated and verified successfully.")


if __name__ == "__main__":
    main()
