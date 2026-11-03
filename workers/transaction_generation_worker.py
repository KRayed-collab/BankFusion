"""
BankFusion Worker: Multi-Bank Transaction Generation & Live Ingestion Worker
=============================================================================
Simulates incoming banking transactions across all THREE heterogeneous banks:
- Bank A (MetroBank): Relational transaction model
- Bank B (QuickPay Bank): Event-stream model with retry linkages
- Bank C (TrustLine Bank): Double-entry balanced ledger journals

Orchestrates scenario distribution planning, 7-stage ETL ingestion pipeline,
fraud detection screening, and deterministic three-tier enforcement policy
execution asynchronously with comprehensive milestone logging and structured diagnostics.
"""

import sys
import time
import random
import logging
import traceback
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from PySide6.QtCore import QThread, Signal

from database.database_connection import SessionLocal, get_active_sqlite_db_path
from database.database_models import (
    BankATransaction,
    BankBEvent,
    BankCLedgerEntry,
    FactTransaction,
    DimTransactionStatus,
    FraudTransactionPrediction,
    TransactionEnforcementRecord,
)
from utils.path_resolver import get_config_path
from etl.map_bank_fields import load_mapping_config
from etl.run_etl_pipeline import execute_full_etl_pipeline
from fraud_detection.save_detection_results import execute_fraud_detection_run
from fraud_detection.demo_auto_block_scenario import inject_controlled_auto_block_scenario
from data_generation.scenario_distribution_planner import (
    ScenarioDistributionPlanner,
    load_simulation_distribution,
)

IST = timezone(timedelta(hours=5, minutes=30))
logger = logging.getLogger("BankFusion.Simulation")


class TransactionGenerationWorker(QThread):
    """
    Executes an end-to-end multi-bank transaction simulation cycle in a background thread.
    Emits signals safely to the Qt GUI thread with comprehensive error reporting.
    """

    generation_completed = Signal(dict)
    generation_failed = Signal(dict)

    def __init__(
        self,
        mode: str = "NORMAL",
        batch_size: int = 3,
        seed: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.mode = mode
        self.batch_size = batch_size
        self.seed = seed
        self._is_interrupted = False

    def stop(self):
        """Signals the worker to abort gracefully."""
        self._is_interrupted = True

    def run(self):
        current_stage = "INITIALIZATION"
        active_db = get_active_sqlite_db_path()
        cfg_path = get_config_path("bank_field_mapping.json")

        try:
            # 1. Controlled Auto-Block Demonstration Mode
            if self.mode == "DEMO_AUTO_BLOCK":
                current_stage = "CONTROLLED_DEMO_SCENARIO"
                logger.info("[SIMULATION] Worker initialized (Mode: DEMO_AUTO_BLOCK)")
                demo_res = inject_controlled_auto_block_scenario()
                self.generation_completed.emit({
                    "success": True,
                    "mode": "DEMO_AUTO_BLOCK",
                    "target_transaction_id": demo_res.get("target_transaction_id", "DEMO-TARGET"),
                    "details": demo_res,
                    "generated_ids": [demo_res.get("target_transaction_id", "DEMO-TARGET")],
                    "primary_transaction_id": demo_res.get("target_transaction_id", "DEMO-TARGET"),
                })
                return

            # 2. Configuration Loading
            current_stage = "CONFIGURATION_LOADING"
            logger.info("[SIMULATION] Start requested")
            mapping_cfg = load_mapping_config()
            dist_cfg = load_simulation_distribution()
            logger.info("[SIMULATION] Configuration loaded")

            # 3. Worker Initialization
            current_stage = "WORKER_INITIALIZATION"
            logger.info("[SIMULATION] Worker initialized")

            if self._is_interrupted:
                return

            # 4. Multi-Bank Synthetic Scenario Generation via ScenarioDistributionPlanner
            current_stage = "DATA_GENERATION"
            planner = ScenarioDistributionPlanner(seed=self.seed)
            plan_res = planner.generate_batch(
                batch_size=self.batch_size,
                anchor_time=datetime.now(IST),
            )

            bank_a_recs = plan_res["bank_a_records"]
            bank_b_recs = plan_res["bank_b_records"]
            bank_c_recs = plan_res["bank_c_records"]
            generated_ids = plan_res["generated_ids"]
            batch_slug = plan_res["batch_slug"]

            # Fallback identifiers for single-record compatibility
            txn_a_id = bank_a_recs[0].transaction_id if bank_a_recs else f"A-TXN-{batch_slug}"
            evt_b_id = bank_b_recs[0].event_id if bank_b_recs else f"B-EVT-{batch_slug}"
            jrn_c_id = bank_c_recs[0].journal_id if bank_c_recs else f"C-JRN-{batch_slug}"

            # Persist generated source records across Banks A, B, and C
            with SessionLocal() as s:
                for rec in bank_a_recs:
                    s.add(rec)
                for rec in bank_b_recs:
                    s.add(rec)
                for rec in bank_c_recs:
                    s.add(rec)
                s.commit()

            logger.info(
                f"[SIMULATION] Synthetic transactions generated "
                f"(Bank A: {txn_a_id}, Bank B: {evt_b_id}, Bank C: {jrn_c_id})"
            )

            if self._is_interrupted:
                return

            # 5. Execute 7-Stage ETL Ingestion Pipeline
            current_stage = "ETL_PIPELINE"
            etl_res = execute_full_etl_pipeline()
            logger.info("[SIMULATION] ETL completed")
            logger.info("[SIMULATION] Warehouse records persisted")

            if self._is_interrupted:
                return

            # 6. Execute Fraud Detection & Enforcement Screening
            current_stage = "FRAUD_DETECTION"
            with SessionLocal() as s:
                det_res = execute_fraud_detection_run(s)
                logger.info("[SIMULATION] Fraud detection completed")

                current_stage = "ENFORCEMENT_POLICY"
                # Screen-Before-Completion Policy:
                # - CLEAR: Simulated processing completes successfully (SUCCESS / RC_00_SUCCESS).
                # - REVIEW_PENDING or AUTO_BLOCKED: Remains held in PENDING state.
                gen_id_set = set(generated_ids)
                enforcements = (
                    s.query(TransactionEnforcementRecord)
                    .filter(
                        TransactionEnforcementRecord.source_transaction_id.in_(gen_id_set),
                        TransactionEnforcementRecord.detection_run_id == det_res.get("detection_run_id"),
                    )
                    .all()
                )

                success_status = (
                    s.query(DimTransactionStatus)
                    .filter_by(status_code="SUCCESS")
                    .first()
                )

                for enf in enforcements:
                    s_id = enf.source_transaction_id
                    if enf.enforcement_status == "CLEAR":
                        # Complete simulated transaction
                        fact = (
                            s.query(FactTransaction)
                            .filter_by(transaction_key=enf.transaction_key)
                            .first()
                        )
                        if fact and success_status:
                            fact.status_key = success_status.status_key

                        if s_id.startswith("A-"):
                            rec_a = s.query(BankATransaction).filter_by(transaction_id=s_id).first()
                            if rec_a:
                                rec_a.transaction_status = "SUCCESS"
                        elif s_id.startswith("B-"):
                            rec_b = s.query(BankBEvent).filter_by(event_id=s_id).first()
                            if rec_b:
                                rec_b.result_code = "RC_00_SUCCESS"
                                rec_b.payment_status = "SUCCESS"

                s.commit()
                logger.info("[SIMULATION] Enforcement completed")

                # 7. Query and Compile Comprehensive Batch Distribution Summary
                predictions = (
                    s.query(FraudTransactionPrediction)
                    .filter(
                        FraudTransactionPrediction.source_transaction_id.in_(gen_id_set),
                        FraudTransactionPrediction.detection_run_id == det_res.get("detection_run_id"),
                    )
                    .all()
                )

                total_gen = len(generated_ids)
                total_screened = len(predictions)
                total_rejected = len(etl_res.get("rejected_records", []))
                total_ingested = total_screened

                # Actual counts by enforcement status
                act_clear = sum(1 for e in enforcements if e.enforcement_status == "CLEAR")
                act_review = sum(1 for e in enforcements if e.enforcement_status == "REVIEW_PENDING")
                act_blocked = sum(1 for e in enforcements if e.enforcement_status == "AUTO_BLOCKED")

                # Actual factor breakdowns
                f0 = sum(1 for p in predictions if p.triggered_factor_count == 0)
                f1 = sum(1 for p in predictions if p.triggered_factor_count == 1)
                f2 = sum(1 for p in predictions if p.triggered_factor_count == 2)
                f3 = sum(1 for p in predictions if p.triggered_factor_count == 3)
                f4 = sum(1 for p in predictions if p.triggered_factor_count == 4)

                denom = total_screened if total_screened > 0 else 1
                pct_clear = round((act_clear / denom) * 100.0, 1)
                pct_review = round((act_review / denom) * 100.0, 1)
                pct_blocked = round((act_blocked / denom) * 100.0, 1)

                tgt_clear = dist_cfg.get("CLEAR", 80.0)
                tgt_review = dist_cfg.get("REVIEW_PENDING", 15.0)
                tgt_blocked = dist_cfg.get("AUTO_BLOCKED", 5.0)

                dev_clear = round(pct_clear - tgt_clear, 1)
                dev_review = round(pct_review - tgt_review, 1)
                dev_blocked = round(pct_blocked - tgt_blocked, 1)

                # Format milestone log table
                summary_log = (
                    f"\n{'='*75}\n"
                    f"[SIMULATION BATCH SUMMARY] Batch: {batch_slug} | Run: {det_res.get('detection_run_id')}\n"
                    f"{'='*75}\n"
                    f"Classification        Target %    Actual Count    Actual %    Deviation\n"
                    f"{'-'*75}\n"
                    f"CLEAR                   {tgt_clear:5.1f}%       {act_clear:6d}         {pct_clear:5.1f}%     {'+' if dev_clear >= 0 else ''}{dev_clear:5.1f}%\n"
                    f"REVIEW_PENDING          {tgt_review:5.1f}%       {act_review:6d}         {pct_review:5.1f}%     {'+' if dev_review >= 0 else ''}{dev_review:5.1f}%\n"
                    f"AUTO_BLOCKED             {tgt_blocked:5.1f}%       {act_blocked:6d}         {pct_blocked:5.1f}%     {'+' if dev_blocked >= 0 else ''}{dev_blocked:5.1f}%\n"
                    f"{'-'*75}\n"
                    f"TOTAL                                  {total_screened:6d}        100.0%\n"
                    f"{'-'*75}\n"
                    f"Triggered Factor Breakdown:\n"
                    f"• 0 Factors: {f0}\n"
                    f"• 1 Factor:  {f1}\n"
                    f"• 2 Factors: {f2}\n"
                    f"• 3 Factors: {f3}\n"
                    f"• 4 Factors: {f4}\n"
                    f"Pipeline Reconciliation:\n"
                    f"• Generated: {total_gen} | Ingested: {total_ingested} | Screened: {total_screened} | Rejected: {total_rejected}\n"
                    f"{'='*75}"
                )
                logger.info(summary_log)

            diag = det_res.get("pipeline_diagnostics", {})
            diag.update({
                "transactions_generated": total_gen,
                "transactions_ingested": total_ingested,
                "transactions_screened": total_screened,
                "transactions_rejected": total_rejected,
                "f0_predictions": f0,
                "f1_predictions": f1,
                "f2_predictions": f2,
                "f3_predictions": f3,
                "f4_predictions": f4,
                "clear_count": act_clear,
                "review_count": act_review,
                "blocked_count": act_blocked,
                "clear_pct": pct_clear,
                "review_pct": pct_review,
                "blocked_pct": pct_blocked,
            })

            result_payload = {
                "success": True,
                "mode": self.mode,
                "batch_size": self.batch_size,
                "batch_slug": batch_slug,
                "generated_ids": generated_ids,
                "primary_transaction_id": txn_a_id,
                "bank_a_id": txn_a_id,
                "bank_b_id": evt_b_id,
                "bank_c_id": jrn_c_id,
                "counts": {
                    "CLEAR": act_clear,
                    "REVIEW_PENDING": act_review,
                    "AUTO_BLOCKED": act_blocked,
                    "TOTAL": total_screened,
                },
                "percentages": {
                    "CLEAR": pct_clear,
                    "REVIEW_PENDING": pct_review,
                    "AUTO_BLOCKED": pct_blocked,
                },
                "targets": {
                    "CLEAR": tgt_clear,
                    "REVIEW_PENDING": tgt_review,
                    "AUTO_BLOCKED": tgt_blocked,
                },
                "deviations": {
                    "CLEAR": dev_clear,
                    "REVIEW_PENDING": dev_review,
                    "AUTO_BLOCKED": dev_blocked,
                },
                "factors": {
                    "0_factors": f0,
                    "1_factor": f1,
                    "2_factors": f2,
                    "3_factors": f3,
                    "4_factors": f4,
                },
                "reconciliation": {
                    "total_generated": total_gen,
                    "total_ingested": total_ingested,
                    "total_screened": total_screened,
                    "total_rejected": total_rejected,
                },
                "etl": etl_res,
                "detection": det_res,
                "pipeline_diagnostics": diag,
                "database_path": str(active_db),
            }

            self.generation_completed.emit(result_payload)

        except Exception as exc:
            tb = traceback.format_exc()
            logger.error(
                f"[SIMULATION_FAILURE] Stage: {current_stage} | "
                f"Exception: {type(exc).__name__}: {exc}\n"
                f"Active Database: {active_db}\n"
                f"Config Path: {cfg_path}\n"
                f"Traceback:\n{tb}"
            )
            self.generation_failed.emit({
                "error_message": str(exc),
                "exception_type": type(exc).__name__,
                "failing_stage": current_stage,
                "traceback": tb,
                "database_path": str(active_db),
                "config_path": str(cfg_path),
            })
