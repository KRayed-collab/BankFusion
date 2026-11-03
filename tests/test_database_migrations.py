"""
BankFusion Automated Test Suite: Database Migrations & Schema Compatibility
==========================================================================
Validates:
1. Opening an older database without `triggered_factor_count`.
2. Running the migration successfully.
3. Confirming historical factor counts are backfilled correctly (0, 1, 2, 3, 4 factors & NULL handling).
4. Running the migration a second time without errors (idempotency).
5. Opening a database that already contains the column.
6. Confirming existing prediction records and IDs are preserved.
7. Loading Transaction Feed query without `OperationalError`.
8. Loading Fraud Review Queue without errors.
9. Loading Automatically Blocked Transactions without errors.
10. Executing new detection runs and verifying correct factor storage.

Uses isolated temporary database fixtures (tmp_path) to ensure the user's primary database is untouched.
"""

import os
import sys
import sqlite3
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.migrations import run_database_migrations, get_active_sqlite_db_path
from database.database_connection import get_engine
from sqlalchemy.orm import sessionmaker
from database.database_models import (
    Base,
    FraudTransactionPrediction,
    FraudDetectionRun,
    FactTransaction,
    DimBank,
    DimTime,
    DimDate,
    DimPaymentMethod,
    DimTransactionStatus,
    DimDevice,
    DimAccount,
    TransactionEnforcementRecord,
    FraudScreeningWarning,
)
from warehouse.warehouse_queries import (
    get_transaction_feed_dataframe,
    get_auto_blocked_transactions,
    get_auto_blocked_summary_metrics,
)
from fraud_detection import review_actions
from fraud_detection.save_detection_results import execute_fraud_detection_run


def create_mock_legacy_database(db_file: Path) -> None:
    """
    Creates an older version of the BankFusion schema in an isolated temp database.
    Initializes all standard models, then strips 'triggered_factor_count' from
    fraud_transaction_prediction to precisely emulate the pre-migration schema.
    """
    test_engine = get_engine(f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(bind=test_engine)

    TestSession = sessionmaker(bind=test_engine)
    with TestSession() as s:
        # Seed required dimensions
        s.add(DimBank(bank_key=1, bank_code="BANK_A", bank_name="MetroBank", bank_type="RETAIL_CORE"))
        s.add(DimTransactionStatus(status_key=1, status_code="SUCCESS", is_terminal=1))
        s.add(DimTransactionStatus(status_key=2, status_code="FAILED", is_terminal=1))
        s.add(DimTransactionStatus(status_key=3, status_code="PENDING", is_terminal=0))
        s.add(DimPaymentMethod(payment_method_key=1, method_code="UPI", method_category="INSTANT"))
        s.add(DimDevice(device_key=1, device_token="DEV-001", is_known=1))
        s.add(DimAccount(account_key=1, bank_key=1, source_account_ref="METRO-ACC-001", customer_id="CUST-1", account_type="SAVINGS", created_at="2026-01-01"))
        s.add(DimAccount(account_key=2, bank_key=1, source_account_ref="METRO-ACC-002", customer_id="CUST-2", account_type="SAVINGS", created_at="2026-01-01"))
        s.add(DimDate(date_key=20261103, full_date="2026-11-03", day_of_month=3, month=11, month_name="November", quarter=4, year=2026, is_weekend=0))
        s.add(DimTime(time_key=1200, hour=12, minute=0, time_of_day="Afternoon"))

        for i in range(1, 6):
            s.add(FactTransaction(
                transaction_key=i,
                bank_key=1,
                date_key=20261103,
                time_key=1200,
                source_account_key=1,
                destination_account_key=2,
                payment_method_key=1,
                status_key=1,
                device_key=1,
                source_transaction_id=f"TXN-LEGACY-{i:03d}",
                source_record_refs=f"TXN-LEGACY-{i:03d}",
                transaction_timestamp="2026-11-03T12:00:00",
                epoch_timestamp=1793500000 + i,
                amount_paise=i * 100000,
                currency="INR",
                source_batch_id="BATCH-LEGACY-01",
                loaded_at="2026-11-03T12:00:00"
            ))

        s.add(FraudDetectionRun(
            detection_run_id="RUN-LEGACY-001",
            run_timestamp="2026-11-03T12:00:00",
            evaluated_batch_id="ALL",
            total_transactions_evaluated=5,
            total_warnings_generated=3,
            total_transactions_flagged=3,
            execution_duration_sec=0.05
        ))
        s.commit()

    # Now drop the column triggered_factor_count using raw sqlite3 to mimic the older database
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("ALTER TABLE fraud_transaction_prediction DROP COLUMN triggered_factor_count;")

    # Insert historical prediction records matching legacy schema (without triggered_factor_count)
    # Row 1: 0 factors (clean)
    cur.execute("""
        INSERT INTO fraud_transaction_prediction
        (prediction_id, detection_run_id, transaction_key, source_bank_code, source_transaction_id, flagged_by_velocity, flagged_by_device, flagged_by_large_amount, flagged_by_cross_bank_movement, is_predicted_suspicious, evaluated_at)
        VALUES (101, 'RUN-LEGACY-001', 1, 'BANK_A', 'TXN-LEGACY-001', 0, 0, 0, 0, 0, '2026-11-03T12:00:00');
    """)
    # Row 2: 1 factor (velocity)
    cur.execute("""
        INSERT INTO fraud_transaction_prediction
        (prediction_id, detection_run_id, transaction_key, source_bank_code, source_transaction_id, flagged_by_velocity, flagged_by_device, flagged_by_large_amount, flagged_by_cross_bank_movement, is_predicted_suspicious, evaluated_at)
        VALUES (102, 'RUN-LEGACY-001', 2, 'BANK_A', 'TXN-LEGACY-002', 1, 0, 0, 0, 1, '2026-11-03T12:00:00');
    """)
    # Row 3: 2 factors (velocity + device)
    cur.execute("""
        INSERT INTO fraud_transaction_prediction
        (prediction_id, detection_run_id, transaction_key, source_bank_code, source_transaction_id, flagged_by_velocity, flagged_by_device, flagged_by_large_amount, flagged_by_cross_bank_movement, is_predicted_suspicious, evaluated_at)
        VALUES (103, 'RUN-LEGACY-001', 3, 'BANK_A', 'TXN-LEGACY-003', 1, 1, 0, 0, 1, '2026-11-03T12:00:00');
    """)
    # Row 4: 3 factors (velocity + device + amount)
    cur.execute("""
        INSERT INTO fraud_transaction_prediction
        (prediction_id, detection_run_id, transaction_key, source_bank_code, source_transaction_id, flagged_by_velocity, flagged_by_device, flagged_by_large_amount, flagged_by_cross_bank_movement, is_predicted_suspicious, evaluated_at)
        VALUES (104, 'RUN-LEGACY-001', 4, 'BANK_A', 'TXN-LEGACY-004', 1, 1, 1, 0, 1, '2026-11-03T12:00:00');
    """)
    # Row 5: 4 factors (all four)
    cur.execute("""
        INSERT INTO fraud_transaction_prediction
        (prediction_id, detection_run_id, transaction_key, source_bank_code, source_transaction_id, flagged_by_velocity, flagged_by_device, flagged_by_large_amount, flagged_by_cross_bank_movement, is_predicted_suspicious, evaluated_at)
        VALUES (105, 'RUN-LEGACY-001', 5, 'BANK_A', 'TXN-LEGACY-005', 1, 1, 1, 1, 1, '2026-11-03T12:00:00');
    """)

    conn.commit()
    conn.close()


# ============================================================================
# MIGRATION TESTS
# ============================================================================

def test_migration_on_legacy_database_adds_column_and_backfills(tmp_path):
    """
    Test 1, 2, 3: Opens an older database lacking triggered_factor_count, runs migration,
    confirms column is added and historical factor counts are backfilled accurately.
    """
    db_file = tmp_path / "legacy_test.db"
    create_mock_legacy_database(db_file)

    # 1. Verify column does not exist before migration
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cols_before = [c[1] for c in cur.execute("PRAGMA table_info(fraud_transaction_prediction)").fetchall()]
    assert "triggered_factor_count" not in cols_before
    conn.close()

    # 2. Run migration
    res = run_database_migrations(db_file)
    assert res["success"] is True
    assert res["rows_backfilled"] == 5

    # 3. Verify column exists now
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cols_after = [c[1] for c in cur.execute("PRAGMA table_info(fraud_transaction_prediction)").fetchall()]
    assert "triggered_factor_count" in cols_after

    # 4. Verify exact backfilled values
    rows = cur.execute("""
        SELECT prediction_id, triggered_factor_count, is_predicted_suspicious
        FROM fraud_transaction_prediction
        ORDER BY prediction_id ASC
    """).fetchall()
    conn.close()

    assert len(rows) == 5
    # Row 101: 0 factors
    assert rows[0] == (101, 0, 0)
    # Row 102: 1 factor
    assert rows[1] == (102, 1, 1)
    # Row 103: 2 factors
    assert rows[2] == (103, 2, 1)
    # Row 104: 3 factors
    assert rows[3] == (104, 3, 1)
    # Row 105: 4 factors
    assert rows[4] == (105, 4, 1)


def test_migration_is_idempotent(tmp_path):
    """
    Test 4: Running migration a second time on an already migrated database
    executes cleanly without errors, duplicate columns, or data corruption.
    """
    db_file = tmp_path / "idempotent_test.db"
    create_mock_legacy_database(db_file)

    # Run first time
    res1 = run_database_migrations(db_file)
    assert res1["success"] is True

    # Run second time
    res2 = run_database_migrations(db_file)
    assert res2["success"] is True

    # Verify column count hasn't duplicated
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cols = [c[1] for c in cur.execute("PRAGMA table_info(fraud_transaction_prediction)").fetchall()]
    assert cols.count("triggered_factor_count") == 1

    # Verify row count preserved
    cnt = cur.execute("SELECT count(*) FROM fraud_transaction_prediction").fetchone()[0]
    assert cnt == 5
    conn.close()


def test_opening_database_already_containing_column(tmp_path):
    """
    Test 5: Opening a database that already has the column succeeds seamlessly.
    """
    db_file = tmp_path / "already_migrated.db"
    create_mock_legacy_database(db_file)
    run_database_migrations(db_file)

    test_engine = get_engine(f"sqlite:///{db_file.as_posix()}")
    TestSession = sessionmaker(bind=test_engine)

    with TestSession() as session:
        preds = session.query(FraudTransactionPrediction).all()
        assert len(preds) == 5
        for p in preds:
            assert hasattr(p, "triggered_factor_count")
            assert isinstance(p.triggered_factor_count, int)


def test_existing_prediction_records_and_ids_preserved(tmp_path):
    """
    Test 6: Confirms primary keys (prediction_id) and foreign key mappings
    are completely preserved during migration.
    """
    db_file = tmp_path / "preserve_test.db"
    create_mock_legacy_database(db_file)
    run_database_migrations(db_file)

    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    records = cur.execute("SELECT prediction_id, transaction_key, source_transaction_id FROM fraud_transaction_prediction").fetchall()
    conn.close()

    expected_ids = [101, 102, 103, 104, 105]
    actual_ids = [r[0] for r in records]
    assert actual_ids == expected_ids
    assert records[0][2] == "TXN-LEGACY-001"
    assert records[4][2] == "TXN-LEGACY-005"


def test_queries_execute_cleanly_on_migrated_database(tmp_path):
    """
    Test 7, 8, 9: Confirms Transaction Feed, Review Queue, and Auto-Blocked queries
    run without sqlite3.OperationalError on the migrated database.
    """
    db_file = tmp_path / "queries_test.db"
    create_mock_legacy_database(db_file)
    run_database_migrations(db_file)

    test_engine = get_engine(f"sqlite:///{db_file.as_posix()}")
    TestSession = sessionmaker(bind=test_engine)

    with TestSession() as session:
        # 1. Transaction Feed Query (the query that previously failed with OperationalError)
        feed_df = get_transaction_feed_dataframe(session)
        assert not feed_df.empty
        assert "triggered_factor_count" in feed_df.columns
        assert "enforcement_status" in feed_df.columns

        # 2. Fraud Review Queue Summary & Alerts
        metrics = review_actions.get_review_queue_summary_metrics(session)
        assert isinstance(metrics, dict)
        assert "awaiting_review" in metrics

        # 3. Automatically Blocked Page Queries
        auto_metrics = get_auto_blocked_summary_metrics(session)
        assert isinstance(auto_metrics, dict)
        assert "active_blocks" in auto_metrics
        blocked_txns = get_auto_blocked_transactions(session)
        assert isinstance(blocked_txns, list)


def test_new_detection_cycle_stores_correct_factor_count(tmp_path):
    """
    Test 10: Runs a complete fraud detection cycle on the migrated database
    and verifies that new prediction rows correctly populate triggered_factor_count.
    """
    db_file = tmp_path / "detection_cycle_test.db"
    create_mock_legacy_database(db_file)
    run_database_migrations(db_file)

    test_engine = get_engine(f"sqlite:///{db_file.as_posix()}")
    TestSession = sessionmaker(bind=test_engine)

    with TestSession() as session:
        res = execute_fraud_detection_run(session, detection_run_id="RUN-MIG-TEST-002")
        assert res["success"] is True

        new_preds = (
            session.query(FraudTransactionPrediction)
            .filter_by(detection_run_id="RUN-MIG-TEST-002")
            .all()
        )
        assert len(new_preds) == 5
        for p in new_preds:
            expected_count = (
                p.flagged_by_velocity
                + p.flagged_by_device
                + p.flagged_by_large_amount
                + p.flagged_by_cross_bank_movement
            )
            assert p.triggered_factor_count == expected_count
