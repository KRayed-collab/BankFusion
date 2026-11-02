"""
BankFusion Automated Test Suite: Phase 5 Fraud Detection & Evaluation
=====================================================================
Validates Rule 1 (Velocity), Rule 2 (Shared Device), Universal Predictions,
and Ground-Truth Evaluation (Confusion Matrix, Precision, Recall, F1).
"""

from database.database_connection import SessionLocal
from database.database_models import FraudTransactionPrediction, FraudScreeningWarning
from data_generation.generate_ground_truth import generate_and_load_full_source_data
from etl.run_etl_pipeline import execute_full_etl_pipeline
from fraud_detection.save_detection_results import execute_fraud_detection_run
from fraud_detection.evaluate_detection_results import evaluate_detection_run


def test_fraud_detection_execution_and_universal_predictions():
    """Validates that fraud detection runs and produces universal predictions for all facts."""
    session = SessionLocal()
    try:
        run_res = execute_fraud_detection_run(session, detection_run_id="TEST-RUN-001")
        assert run_res["status"] == "COMPLETED"
        assert run_res["total_evaluated"] > 0
        assert run_res["total_warnings"] > 0
        assert run_res["flagged_by_velocity"] > 0
        assert run_res["flagged_by_device"] > 0

        # Assert universal prediction count matches evaluated count
        pred_count = (
            session.query(FraudTransactionPrediction)
            .filter_by(detection_run_id="TEST-RUN-001")
            .count()
        )
        assert pred_count == run_res["total_evaluated"]

        # Assert unflagged transactions have is_predicted_suspicious = 0
        unflagged_count = (
            session.query(FraudTransactionPrediction)
            .filter_by(detection_run_id="TEST-RUN-001", is_predicted_suspicious=0)
            .count()
        )
        assert unflagged_count > 0

        # Assert warnings were created
        warning_count = (
            session.query(FraudScreeningWarning)
            .filter_by(detection_run_id="TEST-RUN-001")
            .count()
        )
        assert warning_count == run_res["total_warnings"]
    finally:
        session.close()


def test_ground_truth_evaluation_metrics():
    """Validates confusion matrix and safe metric calculations."""
    session = SessionLocal()
    try:
        eval_res = evaluate_detection_run(session, detection_run_id="TEST-RUN-001")
        assert eval_res["status"] == "COMPLETED"
        assert eval_res["total_evaluated"] > 0
        assert eval_res["tp"] > 0  # Should detect the synthetic velocity & farm cases
        assert eval_res["tn"] > 0  # Should correctly clear the legitimate cases
        assert 0.0 <= eval_res["precision"] <= 1.0
        assert 0.0 <= eval_res["recall"] <= 1.0
        assert 0.0 <= eval_res["f1"] <= 1.0
        assert eval_res["confusion_matrix"]["tp"] == eval_res["tp"]
        assert eval_res["confusion_matrix"]["tn"] == eval_res["tn"]
    finally:
        session.close()

