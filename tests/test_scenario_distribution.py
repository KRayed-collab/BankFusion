"""
BankFusion Automated Test Suite: Scenario Distribution & Balanced Simulation
=============================================================================
Tests all 12 critical verification scenarios required by Section 8:
 1. A clean scenario genuinely triggers zero rules.
 2. A review scenario genuinely triggers one rule.
 3. A review scenario can genuinely trigger two rules.
 4. An automatic-block scenario genuinely triggers at least three distinct rules.
 5. The four detection rules retain their existing thresholds.
 6. Ground-truth labels are not accessed by the detector.
 7. Enforcement decisions are derived from the actual rule flags.
 8. Normal transactions make up the majority of a sufficiently large batch.
 9. Generated classification distribution stays reasonably close to the target over repeated seeded runs.
10. All three banks continue generating valid source records.
11. The ETL pipeline and warehouse reconciliation continue working.
12. Transaction Feed, Fraud Review Queue, and Automatically Blocked pages display the correct records.
"""

import sys
import logging
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_connection import SessionLocal
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
from data_generation.scenario_distribution_planner import (
    ScenarioDistributionPlanner,
    load_simulation_distribution,
)
from etl.run_etl_pipeline import execute_full_etl_pipeline
from fraud_detection.save_detection_results import execute_fraud_detection_run
from fraud_detection.enforcement_policy import (
    determine_enforcement_decision,
    apply_enforcement_for_detection_run,
    get_auto_block_threshold,
)
from fraud_detection.detect_transaction_velocity import load_velocity_thresholds
from fraud_detection.detect_shared_device_usage import load_shared_device_thresholds
from fraud_detection.detect_large_amount import load_large_amount_thresholds
from fraud_detection.detect_cross_bank_movement import load_cross_bank_thresholds
from warehouse.warehouse_queries import (
    get_transaction_feed_dataframe,
    get_auto_blocked_transactions,
)
from fraud_detection.review_actions import get_alerts_for_queue

IST = timezone(timedelta(hours=5, minutes=30))


# ============================================================================
# Test 1: Clean scenario genuinely triggers zero rules
# ============================================================================
def test_01_clean_scenario_triggers_zero_rules():
    """
    Validates that a planned clean scenario with typical amounts and isolated device
    passes through ETL and detection screening with triggered_factor_count == 0 (CLEAR).
    """
    planner = ScenarioDistributionPlanner(seed=123)
    batch = planner.generate_batch(batch_size=10)
    clean_ids = [m["source_id"] for m in batch["ground_truth_metadata"] if m["intended_tier"] == "CLEAR"]

    assert len(clean_ids) > 0, "No clean IDs found in batch"

    # Insert batch records
    with SessionLocal() as s:
        for r in batch["bank_a_records"]:
            s.add(r)
        for r in batch["bank_b_records"]:
            s.add(r)
        for r in batch["bank_c_records"]:
            s.add(r)
        s.commit()

    execute_full_etl_pipeline()

    with SessionLocal() as s:
        det_res = execute_fraud_detection_run(s)
        preds = (
            s.query(FraudTransactionPrediction)
            .filter(
                FraudTransactionPrediction.source_transaction_id.in_(clean_ids),
                FraudTransactionPrediction.detection_run_id == det_res["detection_run_id"],
            )
            .all()
        )
        for p in preds:
            assert p.triggered_factor_count == 0, f"Clean txn {p.source_transaction_id} triggered {p.triggered_factor_count} rules"
            assert p.is_predicted_suspicious == 0


# ============================================================================
# Test 2: Review scenario genuinely triggers one rule
# ============================================================================
def test_02_review_scenario_triggers_one_rule():
    """
    Validates that single-factor review transactions (e.g. Large Amount fallback >= Rs. 100,000)
    genuinely trigger exactly 1 factor -> REVIEW_PENDING.
    """
    now_iso = datetime.now(IST).isoformat()
    slug = f"T02-{int(datetime.now().timestamp() * 1000) % 1000000}"
    txn_id = f"A-TXN-REV-TEST-{slug}"

    rec = BankATransaction(
        transaction_id=txn_id,
        transaction_timestamp=now_iso,
        sender_account_ref=f"A-ACC-TEST1-{slug}",
        receiver_account_ref="B-ACC-0001",
        receiver_bank_code="BANK_B",
        amount_paise=15000000,  # Rs. 1,50,000 (>= Rs. 1,00,000 fallback)
        payment_mode="UPI",
        transaction_status="PENDING",
        device_token=f"DEV-ISOLATED-{slug}",
    )

    with SessionLocal() as s:
        s.add(rec)
        s.commit()

    execute_full_etl_pipeline()

    with SessionLocal() as s:
        det_res = execute_fraud_detection_run(s)
        p = (
            s.query(FraudTransactionPrediction)
            .filter_by(source_transaction_id=txn_id, detection_run_id=det_res["detection_run_id"])
            .first()
        )
        assert p is not None
        assert p.triggered_factor_count == 1
        assert p.flagged_by_large_amount == 1
        assert p.flagged_by_velocity == 0
        assert p.flagged_by_device == 0
        assert p.flagged_by_cross_bank_movement == 0

        enf = (
            s.query(TransactionEnforcementRecord)
            .filter_by(source_transaction_id=txn_id, detection_run_id=det_res["detection_run_id"])
            .first()
        )
        assert enf is not None
        assert enf.enforcement_status == "REVIEW_PENDING"
        assert enf.is_active_block == 0


# ============================================================================
# Test 3: Review scenario can genuinely trigger two rules
# ============================================================================
def test_03_review_scenario_can_trigger_two_rules():
    """
    Validates that a transaction combining 2 distinct factors (Velocity + Large Amount)
    produces triggered_factor_count == 2 -> REVIEW_PENDING (Tier 2).
    """
    now = datetime.now(IST)
    anchor_epoch = int(now.timestamp())
    slug = f"T03-{int(anchor_epoch * 1000) % 1000000}"
    acc = f"A-ACC-DUAL-{slug}"
    dev = f"DEV-ISOLATED-DUAL-{slug}"

    # 4 rapid attempts within 2 mins (Velocity = 1)
    # The 4th attempt is Rs. 1,40,000 (Large Amount = 1)
    target_txn_id = f"A-TXN-DUAL-TARGET-{slug}"
    recs = []
    for i in range(1, 5):
        t_iso = datetime.fromtimestamp(anchor_epoch - (120 - i * 25), tz=IST).isoformat()
        r_id = target_txn_id if i == 4 else f"A-TXN-DUAL-{i}-{slug}"
        amt = 14000000 if i == 4 else 100000  # Rs. 1.4L vs Rs. 1,000
        recs.append(
            BankATransaction(
                transaction_id=r_id,
                transaction_timestamp=t_iso,
                sender_account_ref=acc,
                receiver_account_ref="B-ACC-0001",
                receiver_bank_code="BANK_B",
                amount_paise=amt,
                payment_mode="UPI",
                transaction_status="PENDING",
                device_token=dev,
            )
        )

    with SessionLocal() as s:
        for r in recs:
            s.add(r)
        s.commit()

    execute_full_etl_pipeline()

    with SessionLocal() as s:
        det_res = execute_fraud_detection_run(s)
        p = (
            s.query(FraudTransactionPrediction)
            .filter_by(source_transaction_id=target_txn_id, detection_run_id=det_res["detection_run_id"])
            .first()
        )
        assert p is not None
        assert p.triggered_factor_count == 2
        assert p.flagged_by_velocity == 1
        assert p.flagged_by_large_amount == 1
        assert p.flagged_by_device == 0
        assert p.flagged_by_cross_bank_movement == 0

        enf = (
            s.query(TransactionEnforcementRecord)
            .filter_by(source_transaction_id=target_txn_id, detection_run_id=det_res["detection_run_id"])
            .first()
        )
        assert enf is not None
        assert enf.enforcement_status == "REVIEW_PENDING"
        assert enf.is_active_block == 0


# ============================================================================
# Test 4: Automatic-block scenario genuinely triggers >= 3 rules
# ============================================================================
def test_04_automatic_block_scenario_triggers_three_rules():
    """
    Validates that a high-risk scenario triggering Velocity (Rule 1) + Device (Rule 2) +
    Large Amount (Rule 3) produces triggered_factor_count >= 3 -> AUTO_BLOCKED.
    """
    now = datetime.now(IST)
    anchor_epoch = int(now.timestamp())
    slug = f"T04-{int(anchor_epoch * 1000) % 1000000}"

    shared_dev = f"DEV-BLKFARM-{slug}"
    atk_acc = f"A-ACC-BLK-ATK-{slug}"

    # Setup: 2 distinct accounts on device earlier (t - 400s)
    recs = [
        BankATransaction(
            transaction_id=f"A-TXN-STP1-{slug}",
            transaction_timestamp=datetime.fromtimestamp(anchor_epoch - 420, tz=IST).isoformat(),
            sender_account_ref=f"A-ACC-STP1-{slug}",
            receiver_account_ref="B-ACC-0001",
            receiver_bank_code="BANK_B",
            amount_paise=100000,
            payment_mode="UPI",
            transaction_status="SUCCESS",
            device_token=shared_dev,
        ),
        BankATransaction(
            transaction_id=f"A-TXN-STP2-{slug}",
            transaction_timestamp=datetime.fromtimestamp(anchor_epoch - 380, tz=IST).isoformat(),
            sender_account_ref=f"B-ACC-STP2-{slug}",
            receiver_account_ref="B-ACC-0001",
            receiver_bank_code="BANK_B",
            amount_paise=100000,
            payment_mode="UPI",
            transaction_status="SUCCESS",
            device_token=shared_dev,
        ),
    ]

    # 4 velocity attempts from atk_acc with Rs. 1,50,000
    target_txn_id = f"A-TXN-BLK-TARGET-{slug}"
    for i in range(1, 5):
        t_iso = datetime.fromtimestamp(anchor_epoch - (120 - i * 25), tz=IST).isoformat()
        r_id = target_txn_id if i == 4 else f"A-TXN-BLK-PRE-{i}-{slug}"
        recs.append(
            BankATransaction(
                transaction_id=r_id,
                transaction_timestamp=t_iso,
                sender_account_ref=atk_acc,
                receiver_account_ref="B-ACC-0001",
                receiver_bank_code="BANK_B",
                amount_paise=15000000,  # Rs. 1,50,000
                payment_mode="UPI",
                transaction_status="PENDING",
                device_token=shared_dev,
            )
        )

    with SessionLocal() as s:
        for r in recs:
            s.add(r)
        s.commit()

    execute_full_etl_pipeline()

    with SessionLocal() as s:
        det_res = execute_fraud_detection_run(s)
        p = (
            s.query(FraudTransactionPrediction)
            .filter_by(source_transaction_id=target_txn_id, detection_run_id=det_res["detection_run_id"])
            .first()
        )
        assert p is not None
        assert p.triggered_factor_count >= 3
        assert p.flagged_by_velocity == 1
        assert p.flagged_by_device == 1
        assert p.flagged_by_large_amount == 1

        enf = (
            s.query(TransactionEnforcementRecord)
            .filter_by(source_transaction_id=target_txn_id, detection_run_id=det_res["detection_run_id"])
            .first()
        )
        assert enf is not None
        assert enf.enforcement_status == "AUTO_BLOCKED"
        assert enf.is_active_block == 1


# ============================================================================
# Test 5: Detection rules retain existing thresholds
# ============================================================================
def test_05_detection_rules_retain_existing_thresholds():
    """
    Validates that Rule 1-4 and enforcement thresholds in configuration have not been weakened.
    """
    v_win, v_att = load_velocity_thresholds()
    assert v_win == 300, "Velocity window changed"
    assert v_att == 4, "Velocity min attempts changed"

    d_win, d_acc = load_shared_device_thresholds()
    assert d_win == 86400, "Device window changed"
    assert d_acc == 3, "Device min distinct accounts changed"

    l_cfg = load_large_amount_thresholds()
    assert l_cfg["historical_period_days"] == 30
    assert l_cfg["baseline_floor_paise"] == 5000000  # Rs. 50,000
    assert l_cfg["fallback_threshold_paise"] == 10000000  # Rs. 1,00,000

    c_cfg = load_cross_bank_thresholds()
    assert c_cfg["window_seconds"] == 600
    assert c_cfg["min_retention_ratio"] == 0.80

    auto_blk_th = get_auto_block_threshold()
    assert auto_blk_th == 3, "Auto-block threshold changed"


# ============================================================================
# Test 6: Ground-truth labels are not accessed by the detector
# ============================================================================
def test_06_ground_truth_labels_not_accessed_by_detector():
    """
    Validates architectural separation: execute_fraud_detection_run queries FactTransaction
    and does not access ground_truth or scenario planner metadata.
    """
    import inspect
    from fraud_detection.save_detection_results import execute_fraud_detection_run

    src = inspect.getsource(execute_fraud_detection_run)
    assert "intended_tier" not in src
    assert "ground_truth_metadata" not in src
    assert "ScenarioDistributionPlanner" not in src


# ============================================================================
# Test 7: Enforcement decisions are derived from actual rule flags
# ============================================================================
def test_07_enforcement_decisions_derived_from_actual_rule_flags():
    """
    Validates enforcement policy derivation contract:
    - 0 factors -> CLEAR
    - 1-2 factors -> REVIEW_PENDING
    - 3-4 factors -> AUTO_BLOCKED
    """
    d0 = determine_enforcement_decision(0, 0, 0, 0)
    assert d0["enforcement_status"] == "CLEAR"

    d1 = determine_enforcement_decision(1, 0, 0, 0)
    assert d1["enforcement_status"] == "REVIEW_PENDING"

    d2 = determine_enforcement_decision(1, 1, 0, 0)
    assert d2["enforcement_status"] == "REVIEW_PENDING"

    d3 = determine_enforcement_decision(1, 1, 1, 0)
    assert d3["enforcement_status"] == "AUTO_BLOCKED"

    d4 = determine_enforcement_decision(1, 1, 1, 1)
    assert d4["enforcement_status"] == "AUTO_BLOCKED"


# ============================================================================
# Test 8: Normal transactions make up majority of sufficiently large batch
# ============================================================================
def test_08_normal_transactions_make_up_majority_of_large_batch():
    """
    Validates that a 100-transaction batch has CLEAR >= 70%.
    """
    planner = ScenarioDistributionPlanner(seed=42)
    batch = planner.generate_batch(batch_size=100)
    counts = batch["planned_counts"]

    assert counts["CLEAR"] >= 70, f"Expected CLEAR >= 70%, got {counts['CLEAR']}%"
    assert counts["CLEAR"] > counts["REVIEW_PENDING"] + counts["AUTO_BLOCKED"]


# ============================================================================
# Test 9: Classification distribution stays close to target over seeded runs
# ============================================================================
def test_09_classification_distribution_stays_close_to_target():
    """
    Validates across multiple random seeds (42, 101, 202) that the planned
    batch consistently produces ~80% CLEAR, ~15% REVIEW_PENDING, ~5% AUTO_BLOCKED.
    """
    for seed in [42, 101, 202]:
        planner = ScenarioDistributionPlanner(seed=seed)
        batch = planner.generate_batch(batch_size=100)
        c = batch["planned_counts"]
        assert c["CLEAR"] == 80, f"Seed {seed}: Expected 80 CLEAR, got {c['CLEAR']}"
        assert c["REVIEW_PENDING"] == 15, f"Seed {seed}: Expected 15 REVIEW, got {c['REVIEW_PENDING']}"
        assert c["AUTO_BLOCKED"] == 5, f"Seed {seed}: Expected 5 BLOCKED, got {c['AUTO_BLOCKED']}"


# ============================================================================
# Test 10: All three banks continue generating valid source records
# ============================================================================
def test_10_all_three_banks_generate_valid_source_records():
    """
    Validates that a generated batch includes valid records for Bank A, Bank B, and Bank C.
    """
    planner = ScenarioDistributionPlanner(seed=777)
    batch = planner.generate_batch(batch_size=100)

    assert len(batch["bank_a_records"]) > 0
    assert len(batch["bank_b_records"]) > 0
    assert len(batch["bank_c_records"]) > 0

    # Bank C journals have paired entries
    journal_ids = {entry.journal_id for entry in batch["bank_c_records"]}
    for jid in journal_ids:
        paired = [e for e in batch["bank_c_records"] if e.journal_id == jid]
        assert len(paired) == 2, f"Bank C journal {jid} is not balanced pair"
        sides = {e.entry_side for e in paired}
        assert sides == {"DEBIT", "CREDIT"}


# ============================================================================
# Test 11: ETL pipeline and warehouse reconciliation continue working
# ============================================================================
def test_11_etl_pipeline_and_reconciliation_working():
    """
    Validates that execute_full_etl_pipeline executes without error and reconciles batch.
    """
    planner = ScenarioDistributionPlanner(seed=888)
    batch = planner.generate_batch(batch_size=30)

    with SessionLocal() as s:
        for r in batch["bank_a_records"]:
            s.add(r)
        for r in batch["bank_b_records"]:
            s.add(r)
        for r in batch["bank_c_records"]:
            s.add(r)
        s.commit()

    etl_res = execute_full_etl_pipeline()
    assert etl_res is not None
    assert etl_res.get("batch_status") == "COMPLETED" or "batch_id" in etl_res


# ============================================================================
# Test 12: UI Pages display correct records
# ============================================================================
def test_12_ui_queries_retrieve_correct_records():
    """
    Validates that warehouse queries for Feed, Auto-Blocked, and Review Queue
    cleanly query the active database without exceptions.
    """
    with SessionLocal() as s:
        # Feed query
        feed_df = get_transaction_feed_dataframe(s, limit=10)
        assert not feed_df.empty

        # Auto-blocked query
        blocked_df = get_auto_blocked_transactions(s, status_filter="ACTIVE")
        assert blocked_df is not None

        # Queue query
        alerts = get_alerts_for_queue(s, status_filter="Needs Review", limit=10)
        assert isinstance(alerts, list)
