"""
BankFusion Fraud Detection Manager & Prediction Persistence
============================================================
Coordinates execution of all FOUR detection rules:
- Rule 1: Transaction Velocity Burst (Rolling 5 minutes)
- Rule 2: Shared-Device Abuse (Rolling 24 hours)
- Rule 3: Unusually Large Transaction Amount (Historical baseline / Fallback)
- Rule 4: Rapid Cross-Bank Movement (10-minute linked interbank transfer chains)

Persists entity alerts into fraud_screening_warning with review statuses,
and writes universal transaction-level predictions across all warehouse facts.
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Set
from sqlalchemy.orm import Session

logger = logging.getLogger("BankFusion.DetectionManager")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from warehouse.warehouse_queries import get_denormalized_fact_dataframe
from database.database_models import (
    FraudDetectionRun,
    FraudScreeningWarning,
    FraudTransactionPrediction,
)
from fraud_detection.enforcement_policy import (
    get_auto_block_threshold,
    apply_enforcement_for_detection_run,
)
from fraud_detection.detect_transaction_velocity import (
    detect_velocity_bursts,
    load_velocity_thresholds,
)
from fraud_detection.detect_shared_device_usage import (
    detect_shared_device_abuse,
    load_shared_device_thresholds,
)
from fraud_detection.detect_large_amount import (
    detect_unusually_large_amounts,
    load_large_amount_thresholds,
)
from fraud_detection.detect_cross_bank_movement import (
    detect_rapid_cross_bank_chains,
    load_cross_bank_thresholds,
)


def execute_fraud_detection_run(
    session: Session,
    detection_run_id: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes a complete 4-factor fraud detection screening run.
    Records entity-level alerts and universal transaction predictions.

    Single source of truth return contract:
    {
        "success": True,
        "detection_run_id": "RUN-...",
        "total_transactions_evaluated": int,
        "total_flagged_transactions": int,
        "total_warnings_generated": int,
        "execution_duration_sec": float,
        "error_message": None,
        # Backward-compatible fields
        "status": "COMPLETED",
        "total_evaluated": int,
        "total_warnings": int,
        "flagged_by_velocity": int,
        "flagged_by_device": int,
        "flagged_by_large_amount": int,
        "flagged_by_cross_bank_movement": int,
    }
    """
    start_time = time.time()
    now_str = datetime.now().isoformat()

    if not detection_run_id:
        slug = datetime.now().strftime("%Y%m%d-%H%M%S")
        detection_run_id = f"RUN-{slug}"

    try:
        # 1. Fetch denormalized facts
        df = get_denormalized_fact_dataframe(session, batch_id=batch_id)
        if df.empty:
            duration_sec = round(time.time() - start_time, 3)
            return {
                "success": True,
                "detection_run_id": detection_run_id,
                "total_transactions_evaluated": 0,
                "total_flagged_transactions": 0,
                "total_warnings_generated": 0,
                "execution_duration_sec": duration_sec,
                "error_message": None,
                "status": "NO_TRANSACTIONS",
                "total_evaluated": 0,
                "total_warnings": 0,
                "flagged_by_velocity": 0,
                "flagged_by_device": 0,
                "flagged_by_large_amount": 0,
                "flagged_by_cross_bank_movement": 0,
            }

        # 2. Execute Rule 1 (Velocity Burst - Rolling 5 minutes)
        vel_win, vel_min = load_velocity_thresholds()
        vel_warnings, vel_keys = detect_velocity_bursts(df, window_seconds=vel_win, min_attempts=vel_min)

        # 3. Execute Rule 2 (Shared Device - Rolling 24 hours)
        dev_win, dev_min = load_shared_device_thresholds()
        dev_warnings, dev_keys = detect_shared_device_abuse(df, window_seconds=dev_win, min_distinct_accounts=dev_min)

        # 4. Execute Rule 3 (Unusually Large Amount - Baseline / Fallback)
        large_cfg = load_large_amount_thresholds()
        large_warnings, large_keys = detect_unusually_large_amounts(
            df,
            historical_days=large_cfg.get("historical_period_days", 30),
            min_historical_count=large_cfg.get("min_historical_txns", 5),
            multiplier=large_cfg.get("historical_multiplier", 3.0),
            baseline_floor_paise=large_cfg.get("baseline_floor_paise", 5000000),
            fallback_threshold_paise=large_cfg.get("fallback_threshold_paise", 10000000),
        )

        # 5. Execute Rule 4 (Rapid Cross-Bank Movement - 10-minute linked chains)
        cross_cfg = load_cross_bank_thresholds()
        cross_warnings, cross_keys = detect_rapid_cross_bank_chains(
            df,
            window_seconds=cross_cfg.get("window_seconds", 600),
            min_retention=cross_cfg.get("min_retention_ratio", 0.80),
            max_retention=cross_cfg.get("max_retention_ratio", 1.00),
            min_accounts=cross_cfg.get("min_distinct_accounts", 3),
            min_banks=cross_cfg.get("min_distinct_banks", 2),
        )

        # 6. Map transaction keys to context for alert cards
        txn_context_map = {}
        for _, row in df.iterrows():
            t_k = int(row["transaction_key"])
            txn_context_map[t_k] = {
                "originating_bank": row["bank_code"],
                "destination_bank": row.get("receiver_bank_code") or row["bank_code"],
                "sender_account_ref": row["source_account_ref"],
                "receiver_account_ref": row.get("destination_account_ref") or "UNKNOWN",
                "amount_paise": int(row["amount_paise"]),
                "payment_method": row.get("payment_method", "UNKNOWN"),
                "transaction_status": row.get("transaction_status", "UNKNOWN"),
                "device_token": row.get("device_token"),
                "timestamp": row["transaction_timestamp"],
                "source_transaction_id": row["source_transaction_id"],
            }

        # 7. Consolidate Warnings into Alert Cards (Manual Review Triage: 1-2 rules only)
        threshold = get_auto_block_threshold()
        raw_warning_list = vel_warnings + dev_warnings + large_warnings + cross_warnings
        alert_objects = []

        # Count previous alerts in db to generate human-readable alert_id sequence
        existing_alert_count = session.query(FraudScreeningWarning).count()
        alert_counter = existing_alert_count + 1

        for w in raw_warning_list:
            w_rule = w["rule_name"]

            linked_ids_str = w.get("linked_transaction_ids", "")
            associated_keys = [int(k) for k in linked_ids_str.split(",") if k.strip().isdigit()]

            # Determine all rules triggered for this entity
            rules_for_entity = [w_rule]
            if associated_keys:
                primary_k = associated_keys[0]
                if primary_k in vel_keys and "VELOCITY_BURST" not in rules_for_entity:
                    rules_for_entity.append("VELOCITY_BURST")
                if primary_k in dev_keys and "SHARED_DEVICE" not in rules_for_entity:
                    rules_for_entity.append("SHARED_DEVICE")
                if primary_k in large_keys and "LARGE_AMOUNT" not in rules_for_entity:
                    rules_for_entity.append("LARGE_AMOUNT")
                if primary_k in cross_keys and "CROSS_BANK_MOVEMENT" not in rules_for_entity:
                    rules_for_entity.append("CROSS_BANK_MOVEMENT")

            rule_count = len(rules_for_entity)

            # High-confidence multi-factor fraud (>= threshold) is auto-blocked
            # and routed to the Automatically Blocked page, NOT the manual triage queue.
            if rule_count >= threshold:
                continue

            a_id = f"ALT-{alert_counter:04d}"
            alert_counter += 1

            if rule_count == 2:
                priority = "MEDIUM"
            else:
                priority = "REVIEW"

            # Populate context
            if associated_keys and associated_keys[0] in txn_context_map:
                ctx = txn_context_map[associated_keys[0]]
                orig_b = w.get("originating_bank") or ctx["originating_bank"]
                dest_b = w.get("destination_bank") or ctx["destination_bank"]
                s_acc = w.get("sender_account_ref") or ctx["sender_account_ref"]
                r_acc = w.get("receiver_account_ref") or ctx["receiver_account_ref"]
                amt_p = w.get("amount_paise") or ctx["amount_paise"]
                m_code = w.get("payment_method") or ctx["payment_method"]
                t_stat = w.get("transaction_status") or ctx["transaction_status"]
                dev_tok = w.get("device_token") or ctx["device_token"]
            elif w.get("amount_paise"):
                orig_b = w.get("originating_bank", "UNKNOWN")
                dest_b = w.get("destination_bank", "UNKNOWN")
                s_acc = w.get("sender_account_ref", "UNKNOWN")
                r_acc = w.get("receiver_account_ref", "UNKNOWN")
                amt_p = w.get("amount_paise", 0)
                m_code = w.get("payment_method", "UNKNOWN")
                t_stat = w.get("transaction_status", "UNKNOWN")
                dev_tok = w.get("device_token")
            else:
                orig_b = "METROBANK"
                dest_b = "INTERBANK"
                s_acc = w["entity_ref"]
                r_acc = "VARIOUS"
                amt_p = 0
                m_code = "UPI"
                t_stat = "SUCCESS"
                dev_tok = None

            alert_objects.append(
                FraudScreeningWarning(
                    alert_id=a_id,
                    detection_run_id=detection_run_id,
                    rule_name=w_rule,
                    review_priority=priority,
                    verdict="POTENTIALLY SUSPICIOUS",
                    entity_type=w["entity_type"],
                    entity_ref=w["entity_ref"],
                    trigger_timestamp=w["trigger_timestamp"],
                    window_start=w["window_start"],
                    window_end=w["window_end"],
                    threshold_value=w.get("threshold_value", 0),
                    observed_value=w.get("observed_value", 0),
                    evidence_summary=w["evidence_summary"],
                    originating_bank=orig_b,
                    destination_bank=dest_b,
                    sender_account_ref=s_acc,
                    receiver_account_ref=r_acc,
                    amount_paise=amt_p,
                    payment_method=m_code,
                    transaction_status=t_stat,
                    device_token=dev_tok,
                    rules_triggered=", ".join(rules_for_entity),
                    linked_route_summary=w.get("linked_route_summary"),
                    linked_transaction_ids=w.get("linked_transaction_ids"),
                    review_status="NEEDS_REVIEW",
                )
            )

        # 8. Save FraudDetectionRun metadata
        duration_sec = round(time.time() - start_time, 3)
        all_flagged_keys = vel_keys.union(dev_keys).union(large_keys).union(cross_keys)

        run_obj = FraudDetectionRun(
            detection_run_id=detection_run_id,
            run_timestamp=now_str,
            evaluated_batch_id=batch_id or "ALL",
            total_transactions_evaluated=len(df),
            total_warnings_generated=len(alert_objects),
            total_transactions_flagged=len(all_flagged_keys),
            execution_duration_sec=duration_sec,
        )
        session.add(run_obj)
        session.flush()

        # 9. Bulk Save Alerts
        if alert_objects:
            session.bulk_save_objects(alert_objects)

        # 10. Universal Transaction Predictions (One row per transaction in df)
        # Combined prediction: 1 if ANY of the four rules flagged it, else 0.
        prediction_objects = []
        for _, row in df.iterrows():
            t_key = int(row["transaction_key"])
            in_v = 1 if t_key in vel_keys else 0
            in_d = 1 if t_key in dev_keys else 0
            in_l = 1 if t_key in large_keys else 0
            in_c = 1 if t_key in cross_keys else 0
            is_susp = 1 if (in_v or in_d or in_l or in_c) else 0
            factor_cnt = in_v + in_d + in_l + in_c

            prediction_objects.append(
                FraudTransactionPrediction(
                    detection_run_id=detection_run_id,
                    transaction_key=t_key,
                    source_bank_code=row["bank_code"],
                    source_transaction_id=str(row["source_transaction_id"]),
                    flagged_by_velocity=in_v,
                    flagged_by_device=in_d,
                    flagged_by_large_amount=in_l,
                    flagged_by_cross_bank_movement=in_c,
                    triggered_factor_count=factor_cnt,
                    is_predicted_suspicious=is_susp,
                    evaluated_at=now_str,
                )
            )

        session.bulk_save_objects(prediction_objects)
        session.flush()

        # 11. Three-Tier Fraud Risk Enforcement Policy Application
        enforcement_counts = apply_enforcement_for_detection_run(
            session=session,
            detection_run_id=detection_run_id,
            predictions=prediction_objects,
        )

        session.commit()

        # Verify exact distinct count from database predictions table
        distinct_flagged_count = (
            session.query(FraudTransactionPrediction)
            .filter_by(detection_run_id=detection_run_id, is_predicted_suspicious=1)
            .count()
        )

        # Factor distribution diagnostics
        f0 = sum(1 for p in prediction_objects if p.triggered_factor_count == 0)
        f1 = sum(1 for p in prediction_objects if p.triggered_factor_count == 1)
        f2 = sum(1 for p in prediction_objects if p.triggered_factor_count == 2)
        f3 = sum(1 for p in prediction_objects if p.triggered_factor_count == 3)
        f4 = sum(1 for p in prediction_objects if p.triggered_factor_count == 4)

        pipeline_diagnostics = {
            "detection_run_id": detection_run_id,
            "simulation_batch_id": batch_id or "ALL",
            "enforcement_threshold": threshold,
            "detection_start_time": datetime.fromtimestamp(start_time).isoformat(),
            "detection_completion_time": datetime.now().isoformat(),
            "transactions_evaluated": len(df),
            "transactions_flagged": distinct_flagged_count,
            "factor_0_count": f0,
            "factor_1_count": f1,
            "factor_2_count": f2,
            "factor_3_count": f3,
            "factor_4_count": f4,
            "assigned_clear": enforcement_counts.get("CLEAR", 0),
            "assigned_review_pending": enforcement_counts.get("REVIEW_PENDING", 0),
            "assigned_auto_blocked": enforcement_counts.get("AUTO_BLOCKED", 0),
            "enforcement_persisted": len(prediction_objects),
            "enforcement_failed": 0,
        }

        logger.info(
            f"[PIPELINE_DIAGNOSTICS] Run: {detection_run_id} | Batch: {batch_id or 'ALL'} | "
            f"Evaluated: {len(df)} | Threshold: {threshold} | "
            f"Factors: [0: {f0}, 1: {f1}, 2: {f2}, 3: {f3}, 4: {f4}] | "
            f"Enforcement: [CLEAR: {pipeline_diagnostics['assigned_clear']}, "
            f"REVIEW_PENDING: {pipeline_diagnostics['assigned_review_pending']}, "
            f"AUTO_BLOCKED: {pipeline_diagnostics['assigned_auto_blocked']}] | "
            f"Persisted: {pipeline_diagnostics['enforcement_persisted']} (Failed: 0)"
        )

        return {
            "success": True,
            "detection_run_id": detection_run_id,
            "total_transactions_evaluated": len(df),
            "total_flagged_transactions": distinct_flagged_count,
            "total_warnings_generated": len(alert_objects),
            "enforcement_counts": enforcement_counts,
            "pipeline_diagnostics": pipeline_diagnostics,
            "execution_duration_sec": duration_sec,
            "error_message": None,
            # Backward-compatible fields
            "status": "COMPLETED",
            "total_evaluated": len(df),
            "total_warnings": len(alert_objects),
            "flagged_by_velocity": len(vel_keys),
            "flagged_by_device": len(dev_keys),
            "flagged_by_large_amount": len(large_keys),
            "flagged_by_cross_bank_movement": len(cross_keys),
        }

    except Exception as exc:
        session.rollback()
        duration_sec = round(time.time() - start_time, 3)
        return {
            "success": False,
            "detection_run_id": detection_run_id,
            "total_transactions_evaluated": 0,
            "total_flagged_transactions": 0,
            "total_warnings_generated": 0,
            "execution_duration_sec": duration_sec,
            "error_message": str(exc),
            "status": "FAILED",
            "total_evaluated": 0,
            "total_warnings": 0,
            "flagged_by_velocity": 0,
            "flagged_by_device": 0,
            "flagged_by_large_amount": 0,
            "flagged_by_cross_bank_movement": 0,
        }
