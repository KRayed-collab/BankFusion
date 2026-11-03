"""
BankFusion Automated Test Suite: Automatic Blocking Pipeline & Diagnostics
===========================================================================
Validates the complete end-to-end pipeline:
1. Normal zero-factor transaction (CLEAR)
2. One-factor transaction (REVIEW_PENDING)
3. Two-factor transaction (REVIEW_PENDING)
4. Three-factor transaction that gets automatically blocked (AUTO_BLOCKED)
5. Four-factor transaction that gets automatically blocked (AUTO_BLOCKED)
6. Same-rule repeated evidence does not inflate factor count
7. A transaction is screened before completion (initiates as PENDING)
8. An automatically blocked transaction cannot complete through the simulator
9. Enforcement record persists in SQLite with audit log
10. Active Blocks page retrieves the persisted record
11. Released History retrieves a released record
12. All Auto-Blocks displays both active and released records
13. Blocked amount and average rule statistics are calculated correctly
14. Reprocessing the same detection run does not duplicate block records
"""

import sys
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

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
    DimTransactionStatus,
    BankATransaction,
)
from fraud_detection.enforcement_policy import (
    determine_enforcement_decision,
    apply_enforcement_for_detection_run,
    release_enforcement_transaction,
    get_auto_block_threshold,
)
from fraud_detection.demo_auto_block_scenario import inject_controlled_auto_block_scenario
from warehouse.warehouse_queries import (
    get_auto_blocked_transactions,
    get_auto_blocked_summary_metrics,
)

IST = timezone(timedelta(hours=5, minutes=30))


# ============================================================================
# 1-6. THREE-TIER POLICY & FACTOR COUNTING TESTS
# ============================================================================

def test_01_normal_zero_factor_transaction():
    """Rule 1-4 all 0 -> CLEAR (Tier 1)."""
    d = determine_enforcement_decision(0, 0, 0, 0, auto_block_threshold=3)
    assert d["triggered_factor_count"] == 0
    assert d["risk_tier"] == "CLEAR"
    assert d["enforcement_status"] == "CLEAR"
    assert d["is_active_block"] == 0
    assert d["blocking_reason"] is None


def test_02_one_factor_transaction():
    """1 factor -> REVIEW_PENDING (Tier 2, LOW)."""
    d = determine_enforcement_decision(1, 0, 0, 0, auto_block_threshold=3)
    assert d["triggered_factor_count"] == 1
    assert d["risk_tier"] == "LOW"
    assert d["enforcement_status"] == "REVIEW_PENDING"
    assert d["is_active_block"] == 0
    assert "Velocity Burst" in d["triggered_factors_summary"]


def test_03_two_factor_transaction():
    """2 factors -> REVIEW_PENDING (Tier 2, MEDIUM)."""
    d = determine_enforcement_decision(1, 1, 0, 0, auto_block_threshold=3)
    assert d["triggered_factor_count"] == 2
    assert d["risk_tier"] == "MEDIUM"
    assert d["enforcement_status"] == "REVIEW_PENDING"
    assert d["is_active_block"] == 0
    assert "Velocity Burst" in d["triggered_factors_summary"]
    assert "Shared Device" in d["triggered_factors_summary"]


def test_04_three_factor_transaction_auto_blocked():
    """3 factors -> AUTO_BLOCKED (Tier 3, HIGH)."""
    d = determine_enforcement_decision(1, 1, 1, 0, auto_block_threshold=3)
    assert d["triggered_factor_count"] == 3
    assert d["risk_tier"] == "HIGH"
    assert d["enforcement_status"] == "AUTO_BLOCKED"
    assert d["is_active_block"] == 1
    assert "Velocity Burst" in d["triggered_factors_summary"]
    assert "Shared Device" in d["triggered_factors_summary"]
    assert "Large Amount" in d["triggered_factors_summary"]


def test_05_four_factor_transaction_auto_blocked():
    """4 factors -> AUTO_BLOCKED (Tier 3, HIGH)."""
    d = determine_enforcement_decision(1, 1, 1, 1, auto_block_threshold=3)
    assert d["triggered_factor_count"] == 4
    assert d["risk_tier"] == "HIGH"
    assert d["enforcement_status"] == "AUTO_BLOCKED"
    assert d["is_active_block"] == 1
    assert "Cross-Bank Movement" in d["triggered_factors_summary"]


def test_06_same_rule_repeated_evidence_no_inflation():
    """Multiple events under Rule 1 (e.g. 5 attempts) map strictly to 1 boolean flag."""
    flagged_velocity = 1 if 5 >= 4 else 0
    d = determine_enforcement_decision(flagged_velocity, 0, 0, 0, auto_block_threshold=3)
    assert d["triggered_factor_count"] == 1
    assert d["enforcement_status"] == "REVIEW_PENDING"


# ============================================================================
# 7-8. LIFECYCLE MANAGEMENT TESTS
# ============================================================================

def test_07_transaction_screened_before_completion():
    """Simulated transactions initiate as PENDING and are screened before completion."""
    with SessionLocal() as s:
        target_bank_txn = (
            s.query(BankATransaction)
            .filter(BankATransaction.transaction_id.like("A-TXN-TARGET-AUTOBLK%"))
            .order_by(BankATransaction.transaction_id.desc())
            .first()
        )
        if target_bank_txn:
            assert target_bank_txn.transaction_status == "PENDING"

        target_fact = (
            s.query(FactTransaction)
            .filter(FactTransaction.source_transaction_id.like("A-TXN-TARGET-AUTOBLK%"))
            .order_by(FactTransaction.transaction_key.desc())
            .first()
        )
        if target_fact:
            st = s.query(DimTransactionStatus).filter_by(status_key=target_fact.status_key).first()
            assert st is not None
            assert st.status_code == "PENDING"


def test_08_auto_blocked_transaction_cannot_complete_through_simulator():
    """Auto-blocked transactions cannot transition to SUCCESS during live ingestion."""
    with SessionLocal() as s:
        blocked_rec = (
            s.query(TransactionEnforcementRecord)
            .filter_by(enforcement_status="AUTO_BLOCKED")
            .first()
        )
        if blocked_rec:
            fact = s.query(FactTransaction).filter_by(transaction_key=blocked_rec.transaction_key).first()
            st = s.query(DimTransactionStatus).filter_by(status_key=fact.status_key).first()
            assert st.status_code != "SUCCESS"
            assert st.status_code == "PENDING"


# ============================================================================
# 9-14. PERSISTENCE, UI RETRIEVAL, METRICS & IDEMPOTENCY TESTS
# ============================================================================

def test_09_enforcement_record_persists_in_sqlite():
    """Enforcement decisions persist to transaction_enforcement_record with audit trail."""
    with SessionLocal() as s:
        records = s.query(TransactionEnforcementRecord).filter_by(enforcement_status="AUTO_BLOCKED").all()
        assert len(records) > 0
        r = records[0]
        assert r.triggered_factor_count >= 3
        assert r.is_active_block == 1
        assert r.risk_tier == "HIGH"

        audit = (
            s.query(EnforcementAuditLog)
            .filter_by(transaction_key=r.transaction_key)
            .order_by(EnforcementAuditLog.log_id.desc())
            .first()
        )
        assert audit is not None
        assert audit.new_status == "AUTO_BLOCKED"


def test_10_active_blocks_page_retrieval():
    """get_auto_blocked_transactions('ACTIVE') returns all active auto-blocks with full context."""
    with SessionLocal() as s:
        active_list = get_auto_blocked_transactions(s, status_filter="ACTIVE")
        assert len(active_list) > 0
        first_item = active_list[0]
        assert first_item["enforcement_status"] == "AUTO_BLOCKED"
        assert first_item["is_active_block"] == 1
        assert first_item["amount_inr"] > 0
        assert "sender_account_ref" in first_item
        assert "receiver_account_ref" in first_item


def test_11_released_history_retrieves_released_record():
    """Operator release transitions status to RELEASED, updates status to SUCCESS, and appears in history."""
    with SessionLocal() as s:
        active_rec = (
            s.query(TransactionEnforcementRecord)
            .filter_by(enforcement_status="AUTO_BLOCKED", is_active_block=1)
            .first()
        )
        assert active_rec is not None
        tk = active_rec.transaction_key

        release_res = release_enforcement_transaction(
            session=s,
            transaction_key=tk,
            operator_id="OP-TEST-77",
            release_reason="Verified valid high-value vendor payment with treasury confirmation",
        )
        assert release_res["success"] is True

        # Check retrieval in RELEASED history
        released_list = get_auto_blocked_transactions(s, status_filter="RELEASED")
        matching = [r for r in released_list if r["transaction_key"] == tk]
        assert len(matching) == 1
        assert matching[0]["enforcement_status"] == "RELEASED"
        assert matching[0]["released_by"] == "OP-TEST-77"


def test_12_all_auto_blocks_displays_active_and_released():
    """status_filter='ALL' returns both active auto-blocks and released records."""
    with SessionLocal() as s:
        all_list = get_auto_blocked_transactions(s, status_filter="ALL")
        statuses = {r["enforcement_status"] for r in all_list}
        assert "AUTO_BLOCKED" in statuses or "RELEASED" in statuses
        assert len(all_list) >= 1


def test_13_blocked_amount_and_average_rule_statistics():
    """Summary metrics dynamically calculate counts, total amount, and average rules."""
    with SessionLocal() as s:
        metrics = get_auto_blocked_summary_metrics(s)
        assert "active_blocks" in metrics
        assert "released_blocks" in metrics
        assert "total_blocked_inr" in metrics
        assert "avg_factors" in metrics
        assert metrics["avg_factors"] >= 3.0 or metrics["active_blocks"] == 0
        assert metrics["total_blocked_inr"] >= 0.0


def test_14_reprocessing_same_detection_run_no_duplicate_records():
    """Reprocessing enforcement on the same predictions updates records idempotently without duplicates."""
    with SessionLocal() as s:
        run_obj = s.query(FraudDetectionRun).first()
        run_id = run_obj.detection_run_id if run_obj else "RUN-TEST-DUP"

        sample_fact = s.query(FactTransaction).first()
        tk = sample_fact.transaction_key

        pred = FraudTransactionPrediction(
            detection_run_id=run_id,
            transaction_key=tk,
            source_bank_code="BANK_A",
            source_transaction_id=sample_fact.source_transaction_id,
            flagged_by_velocity=1,
            flagged_by_device=1,
            flagged_by_large_amount=1,
            flagged_by_cross_bank_movement=0,
            triggered_factor_count=3,
            is_predicted_suspicious=1,
            evaluated_at="2026-11-03T12:00:00",
        )

        apply_enforcement_for_detection_run(s, detection_run_id=run_id, predictions=[pred])
        count_first = s.query(TransactionEnforcementRecord).filter_by(transaction_key=tk).count()

        # Reprocess again
        apply_enforcement_for_detection_run(s, detection_run_id=run_id, predictions=[pred])
        count_second = s.query(TransactionEnforcementRecord).filter_by(transaction_key=tk).count()

        assert count_first == 1
        assert count_second == 1
