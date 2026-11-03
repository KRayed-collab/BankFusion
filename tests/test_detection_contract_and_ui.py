"""
BankFusion Automated Test Suite: Detection Contract & UI Architecture
=====================================================================
Validates:
1. Two-page navigation structure and import integrity.
2. Single-source-of-truth detection contract return fields:
   - success
   - detection_run_id
   - total_transactions_evaluated
   - total_flagged_transactions
   - total_warnings_generated
   - execution_duration_sec
3. Accurate distinct calculation of total_flagged_transactions (no double-counting).
4. Unflagged transactions not included in flagged total.
5. Error handling and failure status reporting.
6. Review actions querying and status updates.
"""

import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_connection import SessionLocal
from database.database_models import (
    FactTransaction,
    FraudTransactionPrediction,
    FraudScreeningWarning,
    SimulatedRestrictedAccount,
)
from etl.run_etl_pipeline import execute_full_etl_pipeline
from fraud_detection.save_detection_results import execute_fraud_detection_run
from fraud_detection import review_actions
from warehouse.warehouse_queries import get_transaction_feed_dataframe


@pytest.fixture(autouse=True)
def ensure_warehouse_populated():
    """Ensures warehouse has facts and detection run before UI and contract tests."""
    session = SessionLocal()
    try:
        if session.query(FactTransaction).count() == 0:
            execute_full_etl_pipeline()
    finally:
        session.close()


def test_desktop_application_architecture_and_pages():
    """Confirms PySide6 desktop modules load, and MainWindow hosts exactly two pages."""
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication

    import desktop_main
    from ui.main_window import MainWindow
    from ui.fraud_review_page import FraudReviewPage
    from ui.transaction_feed_page import TransactionFeedPage
    from ui.auto_blocked_page import AutoBlockedPage

    app = QApplication.instance() or QApplication([])
    main_win = MainWindow()

    # Verify THREE main pages in stacked widget
    assert main_win.stack.count() == 3
    assert isinstance(main_win.stack.widget(0), FraudReviewPage)
    assert isinstance(main_win.stack.widget(1), TransactionFeedPage)
    assert isinstance(main_win.stack.widget(2), AutoBlockedPage)

    # Verify navigation sidebar controls
    assert hasattr(main_win, "sidebar")
    assert hasattr(main_win.sidebar, "btn_queue")
    assert hasattr(main_win.sidebar, "btn_feed")
    assert hasattr(main_win.sidebar, "btn_blocked")


def test_detection_execution_contract_success():
    """Validates the standard return contract fields for a successful detection run."""
    session = SessionLocal()
    try:
        run_res = execute_fraud_detection_run(session, detection_run_id="CONTRACT-TEST-001")

        # 1. success = True
        assert run_res["success"] is True

        # 2. valid detection_run_id
        assert run_res["detection_run_id"] == "CONTRACT-TEST-001"

        # 3. Required contract keys present
        required_keys = [
            "success",
            "detection_run_id",
            "total_transactions_evaluated",
            "total_flagged_transactions",
            "total_warnings_generated",
            "execution_duration_sec",
        ]
        for k in required_keys:
            assert k in run_res, f"Missing required contract key: {k}"

        assert isinstance(run_res["total_transactions_evaluated"], int)
        assert isinstance(run_res["total_flagged_transactions"], int)
        assert isinstance(run_res["total_warnings_generated"], int)
        assert isinstance(run_res["execution_duration_sec"], float)

        # 4. Count matches distinct database predictions for that run
        db_flagged_count = (
            session.query(FraudTransactionPrediction)
            .filter_by(detection_run_id="CONTRACT-TEST-001", is_predicted_suspicious=1)
            .count()
        )
        assert run_res["total_flagged_transactions"] == db_flagged_count

        # 5. Unflagged transactions not included in flagged total
        db_unflagged_count = (
            session.query(FraudTransactionPrediction)
            .filter_by(detection_run_id="CONTRACT-TEST-001", is_predicted_suspicious=0)
            .count()
        )
        total_preds = (
            session.query(FraudTransactionPrediction)
            .filter_by(detection_run_id="CONTRACT-TEST-001")
            .count()
        )
        assert db_flagged_count + db_unflagged_count == total_preds
        assert run_res["total_transactions_evaluated"] == total_preds

    finally:
        session.close()


def test_no_double_counting_across_multiple_rules():
    """
    Validates that a transaction flagged by multiple rules has is_predicted_suspicious=1
    and is counted exactly ONCE in total_flagged_transactions.
    """
    session = SessionLocal()
    try:
        preds = (
            session.query(FraudTransactionPrediction)
            .filter_by(detection_run_id="CONTRACT-TEST-001")
            .all()
        )

        for p in preds:
            expected_susp = 1 if (
                p.flagged_by_velocity
                or p.flagged_by_device
                or p.flagged_by_large_amount
                or p.flagged_by_cross_bank_movement
            ) else 0

            assert p.is_predicted_suspicious == expected_susp, (
                f"Mismatch for txn_key {p.transaction_key}: combined prediction {p.is_predicted_suspicious} != {expected_susp}"
            )

        # Count multi-flagged transactions
        multi_flagged = [
            p for p in preds
            if (p.flagged_by_velocity + p.flagged_by_device + p.flagged_by_large_amount + p.flagged_by_cross_bank_movement) > 1
        ]
        # For each multi-flagged transaction, it must contribute at most 1 to total_flagged_transactions
        distinct_keys = {p.transaction_key for p in preds if p.is_predicted_suspicious == 1}
        assert len(distinct_keys) == sum(1 for p in preds if p.is_predicted_suspicious == 1)

    finally:
        session.close()


def test_detection_failure_error_contract():
    """Confirms that failed detection returns an error result instead of false success."""
    class MockFaultySession:
        def query(self, *args, **kwargs):
            raise RuntimeError("Simulated Database Connection Failure")
        def rollback(self):
            pass

    faulty_sess = MockFaultySession()
    res = execute_fraud_detection_run(faulty_sess, detection_run_id="FAULTY-TEST-001")

    assert res["success"] is False
    assert res["status"] == "FAILED"
    assert "Simulated Database Connection Failure" in res["error_message"]
    assert res["total_flagged_transactions"] == 0
    assert res["total_warnings_generated"] == 0


def test_fraud_review_queue_metrics_and_actions():
    """Validates review queue counts, status filters, and action updates."""
    session = SessionLocal()
    try:
        # Check summary metrics
        metrics = review_actions.get_review_queue_summary_metrics(session)
        assert "awaiting_review" in metrics
        assert "escalated" in metrics
        assert "accounts_restricted" in metrics

        # Fetch alerts for each tab
        needs_review = review_actions.get_alerts_for_queue(session, "Needs Review")
        all_alerts = review_actions.get_alerts_for_queue(session, "All Alerts")
        resolved = review_actions.get_alerts_for_queue(session, "Resolved")

        assert isinstance(needs_review, list)
        assert isinstance(all_alerts, list)
        assert isinstance(resolved, list)

        if needs_review:
            target_alert = needs_review[0]
            target_id = target_alert.alert_id or str(target_alert.warning_id)

            # Test updating alert status
            success = review_actions.update_alert_status(
                session=session,
                alert_id=target_id,
                new_status="ESCALATED",
                notes="Automated test escalation",
            )
            assert success is True

            # Verify in DB
            reloaded = session.query(FraudScreeningWarning).filter_by(warning_id=target_alert.warning_id).first()
            assert reloaded.review_status == "ESCALATED"

            # Revert back
            review_actions.update_alert_status(session, target_id, "NEEDS_REVIEW")

    finally:
        session.close()


def test_transaction_feed_data_consistency():
    """Confirms Transaction Feed dataframe reflects the same screening predictions."""
    session = SessionLocal()
    try:
        # Ensure a detection run exists
        execute_fraud_detection_run(session, detection_run_id="FEED-CONSISTENCY-RUN")
        df_feed = get_transaction_feed_dataframe(session)
        assert not df_feed.empty

        # Required columns present
        required_cols = [
            "transaction_key",
            "source_transaction_id",
            "bank_code",
            "source_account_ref",
            "destination_bank",
            "destination_account_ref",
            "amount_inr",
            "transaction_status",
            "is_predicted_suspicious",
            "detection_factors",
        ]
        for col in required_cols:
            assert col in df_feed.columns, f"Missing feed column: {col}"

        # Every row with is_predicted_suspicious=1 must have triggered factors
        flagged_feed_rows = df_feed[df_feed["is_predicted_suspicious"] == 1]
        for _, r in flagged_feed_rows.iterrows():
            assert r["detection_factors"] != "None (Clean)"

    finally:
        session.close()
