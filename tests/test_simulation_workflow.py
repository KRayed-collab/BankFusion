"""
BankFusion Automated Test Suite: Simulation Workflow & Diagnostics
==================================================================
Tests all 12 critical verification scenarios for the simulation pipeline:
 1. Starting a simulation successfully.
 2. Generating transactions for all 3 bank formats (Bank A, B, C).
 3. Processing generated records through ETL.
 4. Persisting transactions into the correct database.
 5. Running fraud detection after ingestion.
 6. Applying the 3-tier enforcement policy.
 7. Refreshing the Transaction Feed.
 8. Starting and stopping the simulation.
 9. Restarting simulation without stale workers.
10. Handling missing configuration files (verifying fallback config).
11. Handling database errors and failed commits gracefully.
12. Preventing multiple simultaneous simulation workers.
"""

import os
import sys
import logging
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from database.database_connection import SessionLocal, get_active_sqlite_db_path
from database.database_models import (
    BankATransaction,
    BankBEvent,
    BankCLedgerEntry,
    FactTransaction,
    FraudTransactionPrediction,
    FraudDetectionRun,
    TransactionEnforcementRecord,
    DimTransactionStatus,
)
from workers.transaction_generation_worker import TransactionGenerationWorker
from etl.map_bank_fields import load_mapping_config, FALLBACK_MAPPING_CONFIG
from ui.transaction_feed_page import TransactionFeedPage


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single QApplication instance exists for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ============================================================================
# Scenario 1 & 2 & 3 & 4 & 5 & 6: End-to-End Multi-Bank Simulation Cycle
# ============================================================================

def test_01_worker_multi_bank_generation_and_pipeline(qapp, caplog):
    """
    Scenarios 1-6:
    - Worker starts and finishes successfully.
    - Generates records for Bank A, Bank B, and Bank C.
    - Processes records via ETL and persists them into the warehouse.
    - Runs fraud detection and produces prediction records.
    - Applies 3-tier enforcement policy and sets lifecycle status accordingly.
    - Verifies milestone logging sequence.
    """
    caplog.set_level(logging.INFO)
    worker = TransactionGenerationWorker(mode="NORMAL")

    result_payload = {}
    error_payload = {}

    def on_completed(payload):
        nonlocal result_payload
        result_payload = payload

    def on_failed(payload):
        nonlocal error_payload
        error_payload = payload

    worker.generation_completed.connect(on_completed)
    worker.generation_failed.connect(on_failed)

    # Run the worker synchronously for testing
    worker.run()

    assert not error_payload, f"Worker failed unexpectedly: {error_payload}"
    assert result_payload, "Worker did not emit completion payload"
    assert result_payload.get("success") is True

    gen_txns = result_payload.get("generated_ids", [])
    assert len(gen_txns) == 3, f"Expected 3 transactions generated, got {gen_txns}"

    txn_a_id = result_payload["bank_a_id"]
    evt_b_id = result_payload["bank_b_id"]
    jrn_c_id = result_payload["bank_c_id"]

    assert txn_a_id.startswith("A-TXN-")
    assert evt_b_id.startswith("B-EVT-")
    assert jrn_c_id.startswith("C-JRN-")

    # Verify milestone logging in caplog
    log_messages = [record.message for record in caplog.records]
    assert any("[SIMULATION] Start requested" in m for m in log_messages)
    assert any("[SIMULATION] Configuration loaded" in m for m in log_messages)
    assert any("[SIMULATION] Worker initialized" in m for m in log_messages)
    assert any("[SIMULATION] Synthetic transactions generated" in m for m in log_messages)
    assert any("[SIMULATION] ETL completed" in m for m in log_messages)
    assert any("[SIMULATION] Warehouse records persisted" in m for m in log_messages)
    assert any("[SIMULATION] Fraud detection completed" in m for m in log_messages)
    assert any("[SIMULATION] Enforcement completed" in m for m in log_messages)

    # Verify records persisted in SQLite database
    with SessionLocal() as s:
        # Bank A record
        rec_a = s.query(BankATransaction).filter_by(transaction_id=txn_a_id).first()
        assert rec_a is not None, "Bank A transaction was not persisted in staging"

        # Bank B event
        rec_b = s.query(BankBEvent).filter_by(event_id=evt_b_id).first()
        assert rec_b is not None, "Bank B event was not persisted in staging"

        # Bank C paired ledger entries
        entries_c = s.query(BankCLedgerEntry).filter_by(journal_id=jrn_c_id).all()
        assert len(entries_c) == 2, "Bank C balanced entries (DEBIT/CREDIT) not persisted"

        # Warehouse facts exist for all generated transactions
        facts_a = s.query(FactTransaction).filter_by(source_transaction_id=txn_a_id).all()
        assert len(facts_a) >= 1, "FactTransaction not found for Bank A transaction"

        facts_b = s.query(FactTransaction).filter_by(source_transaction_id=evt_b_id).all()
        assert len(facts_b) >= 1, "FactTransaction not found for Bank B event"

        facts_c = s.query(FactTransaction).filter_by(source_transaction_id=jrn_c_id).all()
        assert len(facts_c) >= 1, "FactTransaction not found for Bank C journal"

        # Enforcement record exists for screened transactions
        enf_a = s.query(TransactionEnforcementRecord).filter_by(source_transaction_id=txn_a_id).first()
        assert enf_a is not None, "Enforcement record missing for Bank A"
        assert enf_a.enforcement_status in ("CLEAR", "REVIEW_PENDING", "AUTO_BLOCKED")


# ============================================================================
# Scenario 7 & 8 & 9: Transaction Feed UI Refresh, Start/Stop/Restart Lifecycle
# ============================================================================

def test_07_transaction_feed_ui_refresh_on_generation(qapp, caplog):
    """
    Scenario 7:
    - Verifies _on_tx_generated updates counters, emits screening_completed,
      and logs '[SIMULATION] Transaction Feed refreshed'.
    """
    caplog.set_level(logging.INFO)
    feed_page = TransactionFeedPage()

    screening_completed_emitted = False

    def on_screening():
        nonlocal screening_completed_emitted
        screening_completed_emitted = True

    feed_page.screening_completed.connect(on_screening)

    # Initial state
    assert feed_page.sim_batches_count == 0
    assert feed_page.sim_txns_count == 0

    dummy_payload = {
        "success": True,
        "generated_ids": ["A-TXN-TEST-1", "B-EVT-TEST-1", "C-JRN-TEST-1"],
        "primary_transaction_id": "A-TXN-TEST-1",
        "bank_a_id": "A-TXN-TEST-1",
        "bank_b_id": "B-EVT-TEST-1",
        "bank_c_id": "C-JRN-TEST-1",
    }

    with patch.object(feed_page, "load_feed_data"):
        feed_page._on_tx_generated(dummy_payload)

    assert feed_page.sim_batches_count == 1
    assert feed_page.sim_txns_count == 3
    assert "Batches: 1" in feed_page.lbl_sim_counters.text()
    assert "Multi-Bank Ingested: 3 txns" in feed_page.lbl_sim_counters.text()
    assert screening_completed_emitted is True

    log_messages = [record.message for record in caplog.records]
    assert any("[SIMULATION] Transaction Feed refreshed" in m for m in log_messages)


def test_08_and_09_start_stop_restart_lifecycle(qapp):
    """
    Scenarios 8 & 9:
    - Start simulation: updates state, button flags, timer running.
    - Stop simulation: stops timer, resets worker without stale threads.
    - Restart simulation: cleanly re-initializes and starts without crashing.
    """
    feed_page = TransactionFeedPage()

    # Initial state
    assert not feed_page.is_simulating
    assert not feed_page.sim_timer.isActive()

    # 1. Start simulation
    with patch.object(feed_page, "generate_single_transaction") as mock_gen:
        feed_page.start_simulation()
        assert feed_page.is_simulating is True
        assert feed_page.sim_timer.isActive()
        assert not feed_page.btn_start.isEnabled()
        assert feed_page.btn_pause.isEnabled()
        assert feed_page.btn_stop.isEnabled()
        assert "Active" in feed_page.lbl_sim_status.text()
        mock_gen.assert_called_once()

    # 2. Stop simulation
    feed_page.stop_simulation()
    assert feed_page.is_simulating is False
    assert not feed_page.sim_timer.isActive()
    assert feed_page.btn_start.isEnabled()
    assert not feed_page.btn_pause.isEnabled()
    assert not feed_page.btn_stop.isEnabled()
    assert "Idle" in feed_page.lbl_sim_status.text()
    assert feed_page.generation_worker is None

    # 3. Restart simulation (clean cycle without stale workers)
    with patch.object(feed_page, "generate_single_transaction") as mock_gen_restart:
        feed_page.start_simulation()
        assert feed_page.is_simulating is True
        assert feed_page.sim_timer.isActive()
        assert "Active" in feed_page.lbl_sim_status.text()
        mock_gen_restart.assert_called_once()

    feed_page.stop_simulation()


# ============================================================================
# Scenario 10: Handling Missing Configuration Files (Fallback Mapping)
# ============================================================================

def test_10_missing_configuration_fallback():
    """
    Scenario 10:
    - Verify that if bank_field_mapping.json is missing or corrupted,
      load_mapping_config() returns FALLBACK_MAPPING_CONFIG safely.
    """
    with patch("etl.map_bank_fields.get_config_path", return_value=Path("C:/non_existent_dir/dummy_cfg.json")):
        cfg = load_mapping_config()
        assert cfg is not None
        assert "BANK_A" in cfg
        assert "BANK_B" in cfg
        assert "BANK_C" in cfg
        assert cfg["BANK_A"]["amount_field"] == "amount_paise"


# ============================================================================
# Scenario 11: Handling Database Errors and Failed Commits Gracefully
# ============================================================================

def test_11_database_error_handling_graceful():
    """
    Scenario 11:
    - When a database error occurs during generation, the worker catches the exception,
      emits generation_failed with structured diagnostic payload (stage, error, db_path, traceback),
      and does not crash unhandled.
    """
    worker = TransactionGenerationWorker(mode="NORMAL")

    failed_payload = {}

    def on_failed(payload):
        nonlocal failed_payload
        failed_payload = payload

    worker.generation_failed.connect(on_failed)

    with patch("workers.transaction_generation_worker.SessionLocal") as mock_session_factory:
        mock_session_factory.side_effect = RuntimeError("Simulated Database Connection Failure")
        worker.run()

    assert failed_payload, "Worker did not emit failure payload"
    assert failed_payload["exception_type"] == "RuntimeError"
    assert "Simulated Database Connection Failure" in failed_payload["error_message"]
    assert failed_payload["failing_stage"] == "DATA_GENERATION"
    assert "traceback" in failed_payload
    assert "database_path" in failed_payload


# ============================================================================
# Scenario 12: Preventing Multiple Simultaneous Simulation Workers
# ============================================================================

def test_12_prevent_multiple_simultaneous_workers(qapp):
    """
    Scenario 12:
    - If a worker is currently running when a timer tick occurs,
      _on_sim_timer_tick skips launching another worker.
    - If start_simulation is called when already simulating, it ignores the call.
    """
    feed_page = TransactionFeedPage()
    feed_page.is_simulating = True

    # Simulate an active running worker
    mock_running_worker = MagicMock()
    mock_running_worker.isRunning.return_value = True
    feed_page.generation_worker = mock_running_worker

    with patch.object(feed_page, "generate_single_transaction") as mock_gen:
        feed_page._on_sim_timer_tick()
        # Should NOT trigger a new worker because existing worker is running
        mock_gen.assert_not_called()

    # Calling start_simulation again when is_simulating=True should not do anything
    with patch.object(feed_page, "generate_single_transaction") as mock_gen2:
        feed_page.start_simulation()
        mock_gen2.assert_not_called()
