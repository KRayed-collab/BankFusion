"""
BankFusion Page 3: Fraud Intelligence & Rule Evaluation
========================================================
Presents deterministic screening results for Rule 1 (Velocity) and Rule 2 (Shared Device),
universal transaction predictions, and logically separated Ground-Truth evaluation.
"""

import sys
from pathlib import Path
import streamlit as st
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_connection import SessionLocal
from database.database_models import (
    FraudDetectionRun,
    FraudScreeningWarning,
    FraudTransactionPrediction,
)
from fraud_detection.save_detection_results import execute_fraud_detection_run
from fraud_detection.evaluate_detection_results import evaluate_detection_run

st.set_page_config(page_title="Fraud Intelligence | BankFusion", page_icon="🛡️", layout="wide")

st.title("🛡️ Page 3: Fraud Intelligence & Screening Evaluation")
st.caption("Deterministic Rule-Based Screening with Logically Isolated Ground-Truth Evaluation")

session = SessionLocal()

try:
    # Header: Run Controls & Selection
    col_ctrl1, col_ctrl2 = st.columns([1, 2])
    with col_ctrl1:
        if st.button("▶️ Execute New Fraud Detection Run", type="primary"):
            with st.spinner("Screening warehouse transactions against Rule 1 & Rule 2..."):
                run_res = execute_fraud_detection_run(session)
            st.success(f"Detection Run `{run_res['detection_run_id']}` Completed! Flagged: {run_res['total_flagged_transactions']} transactions.")

    # Fetch available detection runs
    runs = session.query(FraudDetectionRun).order_by(FraudDetectionRun.run_timestamp.desc()).all()

    if not runs:
        st.warning("No detection runs available. Click 'Execute New Fraud Detection Run' above or run ETL on Page 2.")
    else:
        run_ids = [r.detection_run_id for r in runs]
        with col_ctrl2:
            selected_run_id = st.selectbox("Select Active Detection Run to Inspect:", run_ids, index=0)

        selected_run = session.query(FraudDetectionRun).filter_by(detection_run_id=selected_run_id).first()

        # Metrics for selected run
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Transactions Evaluated", f"{selected_run.total_transactions_evaluated:,}")
        with m2:
            st.metric("Entity Warnings Generated", f"{selected_run.total_warnings_generated}")
        with m3:
            st.metric("Flagged Transactions", f"{selected_run.total_transactions_flagged}")
        with m4:
            st.metric("Execution Duration", f"{selected_run.execution_duration_sec:.3f}s")

        st.markdown("---")

        tab_warns, tab_preds, tab_eval = st.tabs([
            "1. Rule-Based Warnings & Evidence",
            "2. Universal Transaction Predictions",
            "3. Ground-Truth Evaluation & Confusion Matrix",
        ])

        # =====================================================================
        # TAB 1: WARNINGS & EVIDENCE
        # =====================================================================
        with tab_warns:
            st.subheader("⚠️ Investigator Warnings Summary")
            st.markdown("""
            * **Rule 1 (Velocity Burst):** $\\ge 4$ payment attempts by an account within rolling 300 seconds (includes failed attempts for Banks A and B).
            * **Rule 2 (Shared Device):** $\\ge 3$ distinct sending accounts on the same synthetic hardware token within rolling 24 hours.
            * **Warning Classification:** 1 rule triggered = *Review recommended*; Both rules triggered = *Higher-priority review*.
            """)

            warnings = (
                session.query(FraudScreeningWarning)
                .filter_by(detection_run_id=selected_run_id)
                .all()
            )

            if warnings:
                df_warn = pd.DataFrame([w.__dict__ for w in warnings]).drop(columns=["_sa_instance_state"], errors="ignore")
                st.dataframe(
                    df_warn[[
                        "warning_id", "rule_name", "review_priority", "entity_type", "entity_ref",
                        "trigger_timestamp", "observed_value", "threshold_value", "evidence_summary"
                    ]],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No warnings triggered for this detection run.")

        # =====================================================================
        # TAB 2: UNIVERSAL TRANSACTION PREDICTIONS
        # =====================================================================
        with tab_preds:
            st.subheader("📋 Universal Transaction-Level Predictions")
            st.markdown("""
            To compute a mathematically sound confusion matrix, **every single transaction** in the warehouse
            receives a prediction record (1 or 0). Unflagged transactions are stored with `is_predicted_suspicious = 0`.
            """)

            preds = (
                session.query(FraudTransactionPrediction)
                .filter_by(detection_run_id=selected_run_id)
                .limit(100)
                .all()
            )

            if preds:
                df_pred = pd.DataFrame([p.__dict__ for p in preds]).drop(columns=["_sa_instance_state"], errors="ignore")
                st.dataframe(
                    df_pred[[
                        "prediction_id", "transaction_key", "source_bank_code", "source_transaction_id",
                        "flagged_by_velocity", "flagged_by_device", "is_predicted_suspicious", "evaluated_at"
                    ]],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No predictions found for this run.")

        # =====================================================================
        # TAB 3: GROUND-TRUTH EVALUATION
        # =====================================================================
        with tab_eval:
            st.subheader("🔬 Logically Isolated Ground-Truth Evaluation")
            st.markdown("""
            > [!IMPORTANT]
            > **Academic Integrity:** Operational detection modules have **zero access** to ground-truth labels. 
            > Labels stored in `evaluation_ground_truth` are joined exclusively in this post-hoc evaluation module 
            > to verify that the detector correctly identifies our pre-synthesized controlled scenarios.
            """)

            eval_metrics = evaluate_detection_run(session, detection_run_id=selected_run_id)

            if eval_metrics["status"] == "COMPLETED":
                col_e1, col_e2, col_e3, col_e4 = st.columns(4)
                with col_e1:
                    st.metric("Precision", f"{eval_metrics['precision'] * 100:.2f}%")
                with col_e2:
                    st.metric("Recall", f"{eval_metrics['recall'] * 100:.2f}%")
                with col_e3:
                    st.metric("F1-Score", f"{eval_metrics['f1']:.4f}")
                with col_e4:
                    st.metric("Accuracy", f"{eval_metrics['accuracy'] * 100:.2f}%")

                col_cm, col_fp = st.columns(2)
                with col_cm:
                    st.subheader("Confusion Matrix")
                    st.table(pd.DataFrame(eval_metrics["confusion_matrix"]["matrix"]))
                    st.write(f"**TP:** {eval_metrics['tp']} | **FP:** {eval_metrics['fp']} | **TN:** {eval_metrics['tn']} | **FN:** {eval_metrics['fn']}")

                with col_fp:
                    st.subheader("False Positive Analysis")
                    fp_dict = eval_metrics.get("false_positive_breakdown", {})
                    if fp_dict:
                        st.write("Scenarios triggering benign warnings:")
                        st.json(fp_dict)
                    else:
                        st.success("Zero False Positives in this evaluation slice.")

                st.info(f"💡 **Viva Defense:** {eval_metrics['viva_note']}")

finally:
    session.close()

