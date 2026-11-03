"""
BankFusion Dual Evaluation Engine
=================================
Evaluates two distinct regimes independently:

1. Overall Fraud Detection Performance:
   - Measures detector capability: Did the rule engine recognize risk patterns?
   - Compares: is_predicted_suspicious vs ground_truth.is_suspicious
   - Computes: TP, FP, TN, FN, Precision, Recall, F1, Accuracy, and Confusion Matrix.

2. Automatic Blocking Performance:
   - Measures policy capability: Did the 3-tier threshold safely prevent completion?
   - Compares: enforcement_status == 'AUTO_BLOCKED' vs ground_truth.is_suspicious
   - Computes: Block Precision, Block Recall, Legitimate Blocks, Triage to Human Review,
     Unflagged Misses, Block Rate, Released Overrides, and Blocked Monetary Value.
   - Clarifies: Suspicious transactions with 1-2 factors routed to human review are
     intentional policy triage, NOT detector false negatives or screening failures.
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_models import (
    FraudDetectionRun,
    FraudTransactionPrediction,
    EvaluationGroundTruth,
    TransactionEnforcementRecord,
    FactTransaction,
)


def evaluate_overall_fraud_detection(
    session: Session,
    detection_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates algorithmic fraud detection capability (is_predicted_suspicious vs ground truth).
    Independent of operational enforcement actions.
    """
    if not detection_run_id:
        latest_run = (
            session.query(FraudDetectionRun)
            .order_by(FraudDetectionRun.run_timestamp.desc())
            .first()
        )
        if latest_run:
            detection_run_id = latest_run.detection_run_id
        else:
            return _empty_detection_evaluation("NO_RUNS_FOUND")

    results = (
        session.query(
            FraudTransactionPrediction.transaction_key,
            FraudTransactionPrediction.source_bank_code,
            FraudTransactionPrediction.source_transaction_id,
            FraudTransactionPrediction.flagged_by_velocity,
            FraudTransactionPrediction.flagged_by_device,
            FraudTransactionPrediction.flagged_by_large_amount,
            FraudTransactionPrediction.flagged_by_cross_bank_movement,
            FraudTransactionPrediction.triggered_factor_count,
            FraudTransactionPrediction.is_predicted_suspicious,
            EvaluationGroundTruth.is_suspicious.label("ground_truth_suspicious"),
            EvaluationGroundTruth.scenario_type,
        )
        .join(
            EvaluationGroundTruth,
            (FraudTransactionPrediction.source_bank_code == EvaluationGroundTruth.source_bank_code)
            & (FraudTransactionPrediction.source_transaction_id == EvaluationGroundTruth.source_transaction_id),
        )
        .filter(FraudTransactionPrediction.detection_run_id == detection_run_id)
        .all()
    )

    if not results:
        return _empty_detection_evaluation(detection_run_id)

    df = pd.DataFrame([r._asdict() for r in results])

    pred = df["is_predicted_suspicious"]
    gt = df["ground_truth_suspicious"]

    tp = int(((pred == 1) & (gt == 1)).sum())
    fp = int(((pred == 1) & (gt == 0)).sum())
    tn = int(((pred == 0) & (gt == 0)).sum())
    fn = int(((pred == 0) & (gt == 1)).sum())
    total = tp + fp + tn + fn

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0
    accuracy = round((tp + tn) / total, 4) if total > 0 else 0.0

    # False positive breakdown
    fp_df = df[(pred == 1) & (gt == 0)]
    fp_breakdown = fp_df["scenario_type"].value_counts().to_dict() if not fp_df.empty else {}

    confusion_matrix = {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "matrix": [
            {"actual": "Suspicious (Fraud)", "predicted_suspicious": tp, "predicted_normal": fn},
            {"actual": "Legitimate (Clean)", "predicted_suspicious": fp, "predicted_normal": tn},
        ]
    }

    return {
        "detection_run_id": detection_run_id,
        "status": "COMPLETED",
        "total_evaluated": total,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "confusion_matrix": confusion_matrix,
        "false_positive_breakdown": fp_breakdown,
        "academic_note": (
            "Overall detection measures whether the deterministic multi-bank rules flagged "
            "suspicious patterns regardless of whether the transaction was routed to human review or auto-blocked."
        ),
    }


def evaluate_automatic_blocking(
    session: Session,
    detection_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates the automatic blocking policy against ground-truth labels.
    Measures the precision and coverage of automated intervention.
    """
    if not detection_run_id:
        latest_run = (
            session.query(FraudDetectionRun)
            .order_by(FraudDetectionRun.run_timestamp.desc())
            .first()
        )
        if latest_run:
            detection_run_id = latest_run.detection_run_id
        else:
            return _empty_blocking_evaluation("NO_RUNS_FOUND")

    # Join predictions, enforcement records, and ground truth
    results = (
        session.query(
            FraudTransactionPrediction.transaction_key,
            FraudTransactionPrediction.source_bank_code,
            FraudTransactionPrediction.source_transaction_id,
            FraudTransactionPrediction.triggered_factor_count,
            FraudTransactionPrediction.is_predicted_suspicious,
            TransactionEnforcementRecord.enforcement_status,
            TransactionEnforcementRecord.risk_tier,
            TransactionEnforcementRecord.is_active_block,
            TransactionEnforcementRecord.released_by,
            TransactionEnforcementRecord.release_reason,
            EvaluationGroundTruth.is_suspicious.label("ground_truth_suspicious"),
            EvaluationGroundTruth.scenario_type,
            FactTransaction.amount_paise,
        )
        .join(
            EvaluationGroundTruth,
            (FraudTransactionPrediction.source_bank_code == EvaluationGroundTruth.source_bank_code)
            & (FraudTransactionPrediction.source_transaction_id == EvaluationGroundTruth.source_transaction_id),
        )
        .outerjoin(
            TransactionEnforcementRecord,
            FraudTransactionPrediction.transaction_key == TransactionEnforcementRecord.transaction_key,
        )
        .outerjoin(
            FactTransaction,
            FraudTransactionPrediction.transaction_key == FactTransaction.transaction_key,
        )
        .filter(FraudTransactionPrediction.detection_run_id == detection_run_id)
        .all()
    )

    if not results:
        return _empty_blocking_evaluation(detection_run_id)

    df = pd.DataFrame([r._asdict() for r in results])

    # A transaction was subject to automatic blocking if its status is AUTO_BLOCKED
    # or was initially AUTO_BLOCKED and subsequently RELEASED by an operator.
    was_auto_blocked = df["enforcement_status"].isin(["AUTO_BLOCKED", "RELEASED"])
    is_active_auto_blocked = (df["enforcement_status"] == "AUTO_BLOCKED") & (df["is_active_block"] == 1)
    is_released_block = (df["enforcement_status"] == "RELEASED") & (df["release_reason"].notna())

    gt_suspicious = df["ground_truth_suspicious"] == 1
    gt_legitimate = df["ground_truth_suspicious"] == 0

    total_evaluated = len(df)
    total_gt_suspicious = int(gt_suspicious.sum())
    total_auto_blocked = int(was_auto_blocked.sum())

    # 1. Block Precision: of all transactions auto-blocked, what fraction were genuinely fraudulent?
    auto_blocked_suspicious = int((was_auto_blocked & gt_suspicious).sum())
    block_precision = round(auto_blocked_suspicious / total_auto_blocked, 4) if total_auto_blocked > 0 else 0.0

    # 2. Block Recall: what fraction of all fraudulent transactions were blocked automatically without operator intervention?
    block_recall = round(auto_blocked_suspicious / total_gt_suspicious, 4) if total_gt_suspicious > 0 else 0.0

    # 3. Legitimate transactions auto-blocked (False Blocks / Customer Friction)
    legitimate_auto_blocked = int((was_auto_blocked & gt_legitimate).sum())

    # 4. Suspicious transactions routed to human review (1-2 factors, intentional triage)
    routed_to_review_suspicious = int((~was_auto_blocked & (df["triggered_factor_count"] > 0) & gt_suspicious).sum())

    # 5. Unflagged suspicious (True detector misses / 0 factors)
    unflagged_suspicious = int(((df["triggered_factor_count"] == 0) & gt_suspicious).sum())

    # 6. Auto-Block Rate
    auto_block_rate = round(total_auto_blocked / total_evaluated, 4) if total_evaluated > 0 else 0.0

    # 7. Monetary value of blocked transactions
    blocked_amount_paise = int(df[was_auto_blocked]["amount_paise"].fillna(0).sum())

    # 8. Operator release count
    released_count = int(is_released_block.sum())

    return {
        "detection_run_id": detection_run_id,
        "status": "COMPLETED",
        "total_evaluated": total_evaluated,
        "total_gt_suspicious": total_gt_suspicious,
        "total_auto_blocked": total_auto_blocked,
        "active_auto_blocks": int(is_active_auto_blocked.sum()),
        "released_auto_blocks": released_count,
        "auto_blocked_suspicious": auto_blocked_suspicious,
        "legitimate_auto_blocked": legitimate_auto_blocked,
        "routed_to_review_suspicious": routed_to_review_suspicious,
        "unflagged_suspicious": unflagged_suspicious,
        "block_precision": block_precision,
        "block_recall": block_recall,
        "auto_block_rate": auto_block_rate,
        "blocked_amount_paise": blocked_amount_paise,
        "blocked_amount_inr": blocked_amount_paise / 100.0,
        "triage_clarification": (
            "Important: Suspicious transactions sent to manual review (1-2 factors) are NOT detector false negatives. "
            "They were successfully flagged by the rule engine and intentionally routed to human triage under Tier 2 risk policy."
        ),
    }


def evaluate_detection_run(
    session: Session,
    detection_run_id: str,
) -> Dict[str, Any]:
    """
    Unified evaluation returning both overall detection performance and automatic blocking performance.
    """
    detection_eval = evaluate_overall_fraud_detection(session, detection_run_id)
    blocking_eval = evaluate_automatic_blocking(session, detection_run_id)

    # Legacy compatibility fields from detection_eval
    combined = {**detection_eval}
    combined["overall_detection"] = detection_eval
    combined["automatic_blocking"] = blocking_eval
    return combined


def _empty_detection_evaluation(detection_run_id: str) -> Dict[str, Any]:
    return {
        "detection_run_id": detection_run_id,
        "status": "NO_EVALUATION_DATA",
        "total_evaluated": 0,
        "tp": 0, "fp": 0, "tn": 0, "fn": 0,
        "precision": 0.0, "recall": 0.0, "f1": 0.0,
        "accuracy": 0.0,
        "confusion_matrix": {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "matrix": []},
        "false_positive_breakdown": {},
        "academic_note": "No evaluated transactions found for this run ID.",
    }


def _empty_blocking_evaluation(detection_run_id: str) -> Dict[str, Any]:
    return {
        "detection_run_id": detection_run_id,
        "status": "NO_EVALUATION_DATA",
        "total_evaluated": 0,
        "total_gt_suspicious": 0,
        "total_auto_blocked": 0,
        "active_auto_blocks": 0,
        "released_auto_blocks": 0,
        "auto_blocked_suspicious": 0,
        "legitimate_auto_blocked": 0,
        "routed_to_review_suspicious": 0,
        "unflagged_suspicious": 0,
        "block_precision": 0.0,
        "block_recall": 0.0,
        "auto_block_rate": 0.0,
        "blocked_amount_paise": 0,
        "blocked_amount_inr": 0.0,
        "triage_clarification": "No evaluation records found.",
    }
