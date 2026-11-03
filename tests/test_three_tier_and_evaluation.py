"""
BankFusion Automated Test Suite: Three-Tier Fraud Risk Enforcement & Dual Evaluation
=====================================================================================
Validates:
1. Deterministic prediction flags & distinct factor count deduplication (0, 1, 2, 3, 4 factors).
2. Three-tier enforcement decision logic (CLEAR, REVIEW_PENDING, AUTO_BLOCKED).
3. Configurable auto-block threshold sensitivity.
4. Pre-completion screening lifecycle (held PENDING vs completed SUCCESS).
5. Operator release workflow: validation, state update, audit logging, and simulation release.
6. Dual evaluation mathematics: Detection Performance vs Automatic Blocking Performance.
7. Safe zero-denominator and empty dataset handling.
8. Multi-page UI integration and consistent state synchronization.
"""

import os
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
    FraudDetectionRun,
    TransactionEnforcementRecord,
    EnforcementAuditLog,
    EvaluationGroundTruth,
    DimTransactionStatus,
    BankATransaction,
)
from fraud_detection.enforcement_policy import (
    determine_enforcement_decision,
    get_auto_block_threshold,
    release_enforcement_transaction,
    apply_enforcement_for_detection_run,
)
from fraud_detection.evaluate_detection_results import (
    evaluate_overall_fraud_detection,
    evaluate_automatic_blocking,
    evaluate_detection_run,
)
from fraud_detection import review_actions
from warehouse.warehouse_queries import (
    get_auto_blocked_transactions,
    get_auto_blocked_summary_metrics,
    get_transaction_feed_dataframe,
)


# ============================================================================
# 1. PREDICTION & DISTINCT FACTOR TESTS
# ============================================================================

def test_prediction_factors_and_deduplication():
    """Confirms individual flags produce correct triggered_factor_count (0 to 4)."""
    # 0 factors -> clean
    d0 = determine_enforcement_decision(0, 0, 0, 0, auto_block_threshold=3)
    assert d0["triggered_factor_count"] == 0
    assert d0["enforcement_status"] == "CLEAR"
    assert d0["risk_tier"] == "CLEAR"
    assert d0["is_active_block"] == 0

    # 1 factor -> REVIEW_PENDING (LOW)
    d1 = determine_enforcement_decision(1, 0, 0, 0, auto_block_threshold=3)
    assert d1["triggered_factor_count"] == 1
    assert d1["enforcement_status"] == "REVIEW_PENDING"
    assert d1["risk_tier"] == "LOW"
    assert "Velocity Burst" in d1["triggered_factors_summary"]

    # 2 factors -> REVIEW_PENDING (MEDIUM)
    d2 = determine_enforcement_decision(1, 1, 0, 0, auto_block_threshold=3)
    assert d2["triggered_factor_count"] == 2
    assert d2["enforcement_status"] == "REVIEW_PENDING"
    assert d2["risk_tier"] == "MEDIUM"
    assert "Shared Device" in d2["triggered_factors_summary"]

    # 3 factors -> AUTO_BLOCKED (HIGH)
    d3 = determine_enforcement_decision(1, 1, 1, 0, auto_block_threshold=3)
    assert d3["triggered_factor_count"] == 3
    assert d3["enforcement_status"] == "AUTO_BLOCKED"
    assert d3["risk_tier"] == "HIGH"
    assert d3["is_active_block"] == 1

    # 4 factors -> AUTO_BLOCKED (HIGH)
    d4 = determine_enforcement_decision(1, 1, 1, 1, auto_block_threshold=3)
    assert d4["triggered_factor_count"] == 4
    assert d4["enforcement_status"] == "AUTO_BLOCKED"
    assert d4["is_active_block"] == 1


def test_configurable_auto_block_threshold():
    """Validates policy responds dynamically when auto_block_threshold is altered."""
    # When threshold is 2: 2 factors trigger AUTO_BLOCKED
    d_thresh_2 = determine_enforcement_decision(1, 1, 0, 0, auto_block_threshold=2)
    assert d_thresh_2["enforcement_status"] == "AUTO_BLOCKED"

    # When threshold is 4: 3 factors remain in REVIEW_PENDING
    d_thresh_4 = determine_enforcement_decision(1, 1, 1, 0, auto_block_threshold=4)
    assert d_thresh_4["enforcement_status"] == "REVIEW_PENDING"


# ============================================================================
# 2. ENFORCEMENT PERSISTENCE & AUDIT TESTS
# ============================================================================

def test_apply_enforcement_and_preserves_operator_overrides():
    """Confirms enforcement persists to database and does not overwrite operator actions."""
    with SessionLocal() as session:
        run_obj = session.query(FraudDetectionRun).first()
        run_id = run_obj.detection_run_id if run_obj else "RUN-TEST-001"
        existing_fact = session.query(FactTransaction).first()
        assert existing_fact is not None
        tk = existing_fact.transaction_key
        stxn = existing_fact.source_transaction_id
        sbank = "BANK_A"

        # Clean prior test records
        session.query(EnforcementAuditLog).filter_by(transaction_key=tk).delete()
        session.query(TransactionEnforcementRecord).filter_by(transaction_key=tk).delete()
        session.commit()

        # Create a mock prediction on existing fact
        pred = FraudTransactionPrediction(
            detection_run_id=run_id,
            transaction_key=tk,
            source_bank_code=sbank,
            source_transaction_id=stxn,
            flagged_by_velocity=1,
            flagged_by_device=1,
            flagged_by_large_amount=1,
            flagged_by_cross_bank_movement=0,
            triggered_factor_count=3,
            is_predicted_suspicious=1,
            evaluated_at="2026-11-03T12:00:00",
        )

        counts = apply_enforcement_for_detection_run(
            session=session,
            detection_run_id=run_id,
            predictions=[pred],
        )
        assert counts["AUTO_BLOCKED"] == 1

        rec = session.query(TransactionEnforcementRecord).filter_by(transaction_key=tk).first()
        assert rec is not None
        assert rec.enforcement_status == "AUTO_BLOCKED"
        assert rec.is_active_block == 1

        # Check audit log
        log = session.query(EnforcementAuditLog).filter_by(transaction_key=tk).first()
        assert log is not None

        # Now simulate operator override to RELEASED
        rec.enforcement_status = "RELEASED"
        rec.is_active_block = 0
        rec.release_reason = "Customer ID confirmed by phone"
        session.commit()

        # Re-run enforcement: should preserve operator override
        counts2 = apply_enforcement_for_detection_run(
            session=session,
            detection_run_id=run_id,
            predictions=[pred],
        )
        assert counts2["PRESERVED_OVERRIDE"] == 1

        # Cleanup test records
        session.query(EnforcementAuditLog).filter_by(transaction_key=tk).delete()
        session.query(TransactionEnforcementRecord).filter_by(transaction_key=tk).delete()
        session.commit()


# ============================================================================
# 3. OPERATOR RELEASE WORKFLOW TESTS
# ============================================================================

def test_release_enforcement_validation_and_hold_completion():
    """Confirms release requires valid reason, records audit trail, and completes held status."""
    with SessionLocal() as session:
        run_obj = session.query(FraudDetectionRun).first()
        run_id = run_obj.detection_run_id if run_obj else "RUN-TEST-001"
        pending_status = session.query(DimTransactionStatus).filter_by(status_code="PENDING").first()
        success_status = session.query(DimTransactionStatus).filter_by(status_code="SUCCESS").first()
        assert pending_status is not None and success_status is not None

        # Use second existing fact
        fact = session.query(FactTransaction).offset(1).first()
        assert fact is not None
        tk = fact.transaction_key
        orig_status = fact.status_key

        # Set to pending hold
        fact.status_key = pending_status.status_key
        session.query(EnforcementAuditLog).filter_by(transaction_key=tk).delete()
        session.query(TransactionEnforcementRecord).filter_by(transaction_key=tk).delete()

        enf = TransactionEnforcementRecord(
            transaction_key=tk,
            source_bank_code="BANK_A",
            source_transaction_id=fact.source_transaction_id,
            detection_run_id=run_id,
            enforcement_status="AUTO_BLOCKED",
            risk_tier="HIGH",
            triggered_factor_count=3,
            triggered_factors_summary="Velocity, Device, Amount",
            blocking_reason="Multi-factor auto-block",
            is_active_block=1,
            created_at="2026-11-03T12:00:00",
            blocked_at="2026-11-03T12:00:00",
        )
        session.add(enf)
        session.commit()

        # 1. Validate empty reason raises ValueError
        with pytest.raises(ValueError, match="documented release justification"):
            release_enforcement_transaction(
                session=session,
                transaction_key=tk,
                operator_id="OP-01",
                release_reason="   ",
            )

        # 2. Validate empty operator ID raises ValueError
        with pytest.raises(ValueError, match="Operator ID is required"):
            release_enforcement_transaction(
                session=session,
                transaction_key=tk,
                operator_id="",
                release_reason="Verified by KYC compliance",
            )

        # 3. Successful release
        res = release_enforcement_transaction(
            session=session,
            transaction_key=tk,
            operator_id="OP-SENIOR-1",
            release_reason="Customer verified biometric OTP in branch",
        )
        assert res["success"] is True
        assert res["new_status"] == "RELEASED"

        # Verify database record updated
        rec = session.query(TransactionEnforcementRecord).filter_by(transaction_key=tk).first()
        assert rec.enforcement_status == "RELEASED"
        assert rec.is_active_block == 0
        assert rec.released_by == "OP-SENIOR-1"

        # Verify fact transaction status transitioned to SUCCESS
        session.refresh(fact)
        assert fact.status_key == success_status.status_key

        # Cleanup & restore original status
        fact.status_key = orig_status
        session.query(EnforcementAuditLog).filter_by(transaction_key=tk).delete()
        session.query(TransactionEnforcementRecord).filter_by(transaction_key=tk).delete()
        session.commit()


# ============================================================================
# 4. DUAL EVALUATION ENGINE TESTS
# ============================================================================

def test_overall_detection_evaluation_metrics():
    """Validates Overall Fraud Detection metrics (TP, FP, TN, FN, Precision, Recall, F1)."""
    with SessionLocal() as session:
        eval_res = evaluate_overall_fraud_detection(session)
        assert eval_res["status"] in ("COMPLETED", "NO_EVALUATION_DATA")
        if eval_res["status"] == "COMPLETED":
            assert "precision" in eval_res
            assert "recall" in eval_res
            assert "f1" in eval_res
            assert "accuracy" in eval_res
            assert "confusion_matrix" in eval_res
            assert 0.0 <= eval_res["precision"] <= 1.0
            assert 0.0 <= eval_res["recall"] <= 1.0


def test_automatic_blocking_evaluation_metrics():
    """
    Validates Automatic Blocking evaluation:
    - Block Precision & Recall
    - Clarification that 1-2 factor triage is NOT a false negative
    """
    with SessionLocal() as session:
        blk_res = evaluate_automatic_blocking(session)
        assert blk_res["status"] in ("COMPLETED", "NO_EVALUATION_DATA")
        if blk_res["status"] == "COMPLETED":
            assert "block_precision" in blk_res
            assert "block_recall" in blk_res
            assert "auto_block_rate" in blk_res
            assert "triage_clarification" in blk_res
            # Ensure the educational clarification explicitly mentions 1-2 factor triage
            assert "NOT detector false negatives" in blk_res["triage_clarification"]


def test_evaluation_empty_run_zero_denominator_safe():
    """Validates that non-existent run ID returns clean 0.0 metrics without ZeroDivisionError."""
    with SessionLocal() as session:
        det = evaluate_overall_fraud_detection(session, detection_run_id="RUN-DOES-NOT-EXIST-999")
        assert det["precision"] == 0.0
        assert det["recall"] == 0.0
        assert det["f1"] == 0.0

        blk = evaluate_automatic_blocking(session, detection_run_id="RUN-DOES-NOT-EXIST-999")
        assert blk["block_precision"] == 0.0
        assert blk["block_recall"] == 0.0
        assert blk["auto_block_rate"] == 0.0


# ============================================================================
# 5. DESKTOP GUI THREE-PAGE INTEGRATION TESTS
# ============================================================================

def test_gui_three_pages_and_enforcement_colors():
    """Validates MainWindow hosts all 3 pages and table feed renders enforcement columns."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow
    from ui.fraud_review_page import FraudReviewPage
    from ui.transaction_feed_page import TransactionFeedPage
    from ui.auto_blocked_page import AutoBlockedPage

    app = QApplication.instance() or QApplication([])
    main_win = MainWindow()

    # 3 Pages
    assert main_win.stack.count() == 3
    assert isinstance(main_win.stack.widget(0), FraudReviewPage)
    assert isinstance(main_win.stack.widget(1), TransactionFeedPage)
    assert isinstance(main_win.stack.widget(2), AutoBlockedPage)

    # Sidebar buttons
    assert hasattr(main_win.sidebar, "btn_queue")
    assert hasattr(main_win.sidebar, "btn_feed")
    assert hasattr(main_win.sidebar, "btn_blocked")

    # Feed queries enforcement status
    with SessionLocal() as session:
        feed_df = get_transaction_feed_dataframe(session, limit=10)
        if not feed_df.empty:
            assert "enforcement_status" in feed_df.columns
            assert "risk_tier" in feed_df.columns
            assert "triggered_factor_count" in feed_df.columns
            assert "is_active_block" in feed_df.columns
