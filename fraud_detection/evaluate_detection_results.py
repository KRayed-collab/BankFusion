"""
BankFusion Fraud Detection Evaluation Engine
============================================
Evaluates operational predictions against logically separated ground-truth labels.
Computes True Positives, False Positives, True Negatives, False Negatives,
Precision, Recall, F1-score, and detailed False-Positive breakdowns.

1. What the file does:
   Joins fraud_transaction_prediction with evaluation_ground_truth on
   (source_bank_code, source_transaction_id) for a selected detection_run_id.
   Calculates the complete confusion matrix and classification metrics.
2. Why it exists:
   Provides academic validation of the rule engine against synthetic target scenarios
   without leaking ground-truth labels into operational screening logic.
3. What inputs it accepts:
   - session: Active SQLAlchemy session
   - detection_run_id: Identifier of the run to evaluate
4. What output it produces:
   Dictionary containing TP, FP, TN, FN, precision, recall, f1, confusion matrix,
   and false-positive scenario breakdowns.
5. Which other files call it:
   Called by Streamlit Page 3, demo runner, and test suites.
6. Which DWM concept it demonstrates:
   Classification performance evaluation, confusion matrix mathematics, and synthetic data validation limitations.
7. How a student can explain it during a viva:
   "We evaluate our screening rules by comparing predictions against our isolated ground-truth labels.
   Because our data is synthetic, strong precision and recall confirm our logic works as intended,
   but real banking deployment would require calibration on real-world, uncurated data."
"""

import sys
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_models import (
    FraudTransactionPrediction,
    EvaluationGroundTruth,
)


def evaluate_detection_run(
    session: Session,
    detection_run_id: str,
) -> Dict[str, Any]:
    """
    Computes confusion matrix and precision/recall metrics for a specific detection run.
    """
    # Query joined predictions and ground truth
    results = (
        session.query(
            FraudTransactionPrediction.transaction_key,
            FraudTransactionPrediction.source_bank_code,
            FraudTransactionPrediction.source_transaction_id,
            FraudTransactionPrediction.flagged_by_velocity,
            FraudTransactionPrediction.flagged_by_device,
            FraudTransactionPrediction.flagged_by_large_amount,
            FraudTransactionPrediction.flagged_by_cross_bank_movement,
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
        return {
            "detection_run_id": detection_run_id,
            "status": "NO_EVALUATION_DATA",
            "tp": 0, "fp": 0, "tn": 0, "fn": 0,
            "precision": 0.0, "recall": 0.0, "f1": 0.0,
            "accuracy": 0.0,
            "total_evaluated": 0,
            "false_positive_breakdown": {},
        }

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

    # False positive breakdown by scenario type
    fp_df = df[(pred == 1) & (gt == 0)]
    fp_breakdown = fp_df["scenario_type"].value_counts().to_dict() if not fp_df.empty else {}

    confusion_matrix = {
        "matrix": [
            {"Actual": "Suspicious (1)", "Predicted Suspicious": tp, "Predicted Normal": fn},
            {"Actual": "Legitimate (0)", "Predicted Suspicious": fp, "Predicted Normal": tn},
        ],
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }

    academic_viva_note = (
        "Academic Context: Our evaluation dataset contains programmatically generated scenarios. "
        "High metrics validate the algorithmic implementation of our velocity and shared-device logic, "
        "but do not constitute proof of real-world banking performance where fraud patterns evolve adaptively."
    )

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
        "viva_note": academic_viva_note,
    }

