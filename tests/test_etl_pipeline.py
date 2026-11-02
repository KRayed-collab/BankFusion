"""
BankFusion Automated Test Suite: Phase 3 ETL Pipeline
=====================================================
Validates extraction, validation, Bank C pairing, dual lineage,
duplicate prevention, and dual-equation reconciliation balances.
"""

from database.database_connection import SessionLocal
from database.database_models import FactTransaction, ETLBatchLog, ETLRejectedRecord
from data_generation.generate_ground_truth import generate_and_load_full_source_data
from etl.run_etl_pipeline import execute_full_etl_pipeline
from etl.pair_bank_c_ledger_entries import pair_and_validate_bank_c_journals


def test_bank_c_pairing_and_edge_case_quarantine():
    """Validates that valid journals produce 1 transfer while corrupted legs are quarantined."""
    test_entries = [
        # Valid Journal 1 (Normal)
        {
            "entry_id": "C-T-01", "journal_id": "J-01", "posting_timestamp": "2026-11-01T12:00:00+05:30",
            "ledger_account_ref": "ACC-1", "counterparty_account_ref": "ACC-2",
            "counterparty_bank_code": "BANK_C", "entry_side": "DEBIT", "amount_paise": 100000,
            "currency": "INR", "transfer_type": "BOOK_TRANSFER", "entry_status": "POSTED", "device_token": None
        },
        {
            "entry_id": "C-T-02", "journal_id": "J-01", "posting_timestamp": "2026-11-01T12:00:00+05:30",
            "ledger_account_ref": "ACC-2", "counterparty_account_ref": "ACC-1",
            "counterparty_bank_code": "BANK_C", "entry_side": "CREDIT", "amount_paise": 100000,
            "currency": "INR", "transfer_type": "BOOK_TRANSFER", "entry_status": "POSTED", "device_token": None
        },
        # Corrupted Journal 2 (Mismatched amounts)
        {
            "entry_id": "C-T-03", "journal_id": "J-02", "posting_timestamp": "2026-11-01T12:05:00+05:30",
            "ledger_account_ref": "ACC-3", "counterparty_account_ref": "ACC-4",
            "counterparty_bank_code": "BANK_C", "entry_side": "DEBIT", "amount_paise": 200000,
            "currency": "INR", "transfer_type": "BOOK_TRANSFER", "entry_status": "POSTED", "device_token": None
        },
        {
            "entry_id": "C-T-04", "journal_id": "J-02", "posting_timestamp": "2026-11-01T12:05:00+05:30",
            "ledger_account_ref": "ACC-4", "counterparty_account_ref": "ACC-3",
            "counterparty_bank_code": "BANK_C", "entry_side": "CREDIT", "amount_paise": 190000,
            "currency": "INR", "transfer_type": "BOOK_TRANSFER", "entry_status": "POSTED", "device_token": None
        },
    ]

    res = pair_and_validate_bank_c_journals(test_entries, batch_id="TEST-PAIR-BATCH")
    assert len(res["paired_transfers"]) == 1
    assert res["paired_transfers"][0]["journal_id"] == "J-01"
    assert res["paired_transfers"][0]["source_record_refs"] == "C-T-01,C-T-02"
    assert len(res["pairing_rejections"]) == 2  # Both legs of J-02 quarantined
    assert "MISMATCHED_AMOUNTS" in res["pairing_rejections"][0]["rejection_reason"]


def test_full_etl_execution_and_reconciliation_balance():
    """Validates end-to-end ETL execution and assert equation balances."""
    # Reset and seed source tables
    generate_and_load_full_source_data(random_seed=42, reset_tables=True)

    summary = execute_full_etl_pipeline(batch_id="TEST-ETL-RUN-1")
    assert summary["batch_status"] == "COMPLETED"
    assert summary["equation_1_source_balanced"] is True
    assert summary["equation_2_load_balanced"] is True
    assert summary["monetary_reconciliation_balanced"] is True
    assert summary["warehouse_inserted"] > 0
    assert summary["duplicates_skipped"] == 0

    session = SessionLocal()
    try:
        fact_count = session.query(FactTransaction).count()
        assert fact_count == summary["warehouse_inserted"]
        
        # Check that Bank C records in FactTransaction have comma-separated lineage
        bank_c_fact = session.query(FactTransaction).join(FactTransaction.bank).filter_by(bank_code="BANK_C").first()
        assert bank_c_fact is not None
        assert "," in bank_c_fact.source_record_refs
        assert bank_c_fact.source_transaction_id.startswith("C-J-")
    finally:
        session.close()


def test_idempotent_etl_duplicate_prevention():
    """Validates that re-running ETL on existing records skips 100% of duplicates."""
    summary_replay = execute_full_etl_pipeline(batch_id="TEST-ETL-RUN-REPLAY")
    assert summary_replay["batch_status"] == "COMPLETED"
    assert summary_replay["warehouse_inserted"] == 0
    assert summary_replay["duplicates_skipped"] > 0
    assert summary_replay["equation_2_load_balanced"] is True
    assert summary_replay["duplicate_amount_paise"] > 0
    assert summary_replay["warehouse_amount_paise"] == 0

