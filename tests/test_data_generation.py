"""
BankFusion Automated Test Suite: Phase 1 Data Generation
========================================================
Validates that synthetic data generators produce correct, reproducible,
and schema-compliant records for all three bank source systems and ground truth.
"""

import pytest
from datetime import datetime
from database.database_connection import SessionLocal
from database.database_models import (
    BankATransaction,
    BankBEvent,
    BankCLedgerEntry,
    EvaluationGroundTruth,
    DimBank,
    DimTime,
)
from data_generation.generate_customers_and_accounts import generate_customer_and_account_pools
from data_generation.generate_bank_a_data import generate_bank_a_transactions
from data_generation.generate_bank_b_data import generate_bank_b_events
from data_generation.generate_bank_c_ledger import generate_bank_c_ledger_entries
from data_generation.generate_ground_truth import generate_and_load_full_source_data


def test_customer_and_account_pools_reproducibility():
    """Validates that pools are identical across identical random seeds."""
    pool1 = generate_customer_and_account_pools(num_customers=30, num_devices=15, random_seed=42)
    pool2 = generate_customer_and_account_pools(num_customers=30, num_devices=15, random_seed=42)

    assert len(pool1["customers"]) == 30
    assert len(pool1["devices"]) == 15
    assert pool1["customers"][0] == pool2["customers"][0]
    assert pool1["accounts"]["BANK_A"][0] == pool2["accounts"]["BANK_A"][0]


def test_bank_a_data_structure_and_constraints():
    """Validates Bank A transaction fields, types, and amounts."""
    pools = generate_customer_and_account_pools(random_seed=42)
    txns = generate_bank_a_transactions(pools["accounts"], pools["devices"], num_records=25, random_seed=42)

    assert len(txns) == 25
    for t in txns:
        assert t["transaction_id"].startswith("A-TXN-")
        assert t["sender_account_ref"].startswith("A-ACC-")
        assert t["receiver_bank_code"] in ["BANK_A", "BANK_B", "BANK_C"]
        assert isinstance(t["amount_paise"], int)
        assert t["amount_paise"] > 0
        assert t["payment_mode"] in ["UPI", "IMPS", "NEFT", "RTGS", "CARD"]
        assert t["transaction_status"] in ["SUCCESS", "FAILED", "PENDING"]
        # Validate ISO timestamp parseability
        dt = datetime.fromisoformat(t["transaction_timestamp"])
        assert dt is not None


def test_bank_b_event_retries():
    """Validates Bank B event structure and multi-event retry relationships."""
    pools = generate_customer_and_account_pools(random_seed=42)
    events = generate_bank_b_events(pools["accounts"], pools["devices"], num_requests=30, random_seed=42)

    assert len(events) >= 30
    request_refs = {}
    for e in events:
        assert e["event_id"].startswith("B-EVT-")
        assert e["sender_wallet_ref"].startswith("B-ACC-")
        assert isinstance(e["value_paise"], int)
        assert e["value_paise"] > 0
        assert e["result_code"] in ["RC_00_SUCCESS", "RC_05_FAILED", "RC_99_PENDING"]
        
        req = e["payment_request_ref"]
        request_refs[req] = request_refs.get(req, 0) + 1

    # At least some payment requests should have retries (> 1 event)
    has_retries = any(count > 1 for count in request_refs.values())
    assert has_retries, "Expected some Bank B payment requests to simulate retry events."


def test_bank_c_ledger_pairing():
    """Validates Bank C double-entry pairs, equal amounts, and reciprocal accounts."""
    pools = generate_customer_and_account_pools(random_seed=42)
    entries = generate_bank_c_ledger_entries(
        pools["accounts"],
        pools["devices"],
        num_journals=20,
        include_malformed=False,
        random_seed=42,
    )

    assert len(entries) == 40  # 20 journals * 2 legs = 40 entries
    by_journal = {}
    for entry in entries:
        assert entry["counterparty_bank_code"] == "BANK_C"
        assert entry["entry_side"] in ["DEBIT", "CREDIT"]
        assert isinstance(entry["amount_paise"], int)
        assert entry["amount_paise"] > 0
        j_id = entry["journal_id"]
        by_journal.setdefault(j_id, []).append(entry)

    for j_id, legs in by_journal.items():
        assert len(legs) == 2, f"Journal {j_id} must have exactly 2 legs."
        sides = {legs[0]["entry_side"], legs[1]["entry_side"]}
        assert sides == {"DEBIT", "CREDIT"}, f"Journal {j_id} must contain 1 DEBIT and 1 CREDIT."
        assert legs[0]["amount_paise"] == legs[1]["amount_paise"], "Leg amounts must be identical."
        
        # Check reciprocal counterparty references
        debit_leg = legs[0] if legs[0]["entry_side"] == "DEBIT" else legs[1]
        credit_leg = legs[1] if legs[0]["entry_side"] == "DEBIT" else legs[0]
        assert debit_leg["ledger_account_ref"] == credit_leg["counterparty_account_ref"]
        assert credit_leg["ledger_account_ref"] == debit_leg["counterparty_account_ref"]


def test_full_database_load_and_ground_truth_isolation():
    """Validates end-to-end master generation and physical database counts."""
    summary = generate_and_load_full_source_data(random_seed=42, reset_tables=True)
    assert summary["status"] == "SUCCESS"

    session = SessionLocal()
    try:
        # Check source tables
        count_a = session.query(BankATransaction).count()
        count_b = session.query(BankBEvent).count()
        count_c = session.query(BankCLedgerEntry).count()
        count_gt = session.query(EvaluationGroundTruth).count()
        count_banks = session.query(DimBank).count()
        count_times = session.query(DimTime).count()

        assert count_a == summary["bank_a_records_generated"]
        assert count_b == summary["bank_b_events_generated"]
        assert count_c == summary["bank_c_entries_generated"]
        assert count_gt == summary["ground_truth_records_stored"]
        assert count_banks == 3
        assert count_times == 1440  # 24 * 60 minutes seeded

        # Check ground-truth composition
        suspicious_count = session.query(EvaluationGroundTruth).filter_by(is_suspicious=1).count()
        legit_count = session.query(EvaluationGroundTruth).filter_by(is_suspicious=0).count()
        assert suspicious_count > 0, "Must contain suspicious scenarios."
        assert legit_count > 0, "Must contain legitimate baseline scenarios."
        assert (suspicious_count + legit_count) == count_gt

    finally:
        session.close()

