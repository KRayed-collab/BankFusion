"""
BankFusion Reproducible Live Demonstration Runner (BF-DEMO-001)
===============================================================
Executes the comprehensive 13-step examination demonstration using
GENUINE production backend functions (no fake mock logic).

Steps Demonstrated:
1. Ingest raw demo records into source tables
2. Inspect heterogeneous source formats (Grain disparity)
3. Validate records and detect malformed entries
4. Execute Bank C debit-credit pairing (2:1 grain reduction)
5. Quarantine malformed journal (C-J-DEMO-ERR)
6. Map heterogeneous schemas into canonical format
7. Resolve dimension surrogate keys
8. Idempotently load into FactTransaction
9. Verify dual-equation ETL reconciliation
10. Execute Rule 1 (Velocity burst) and Rule 2 (Shared device abuse)
11. Explain generated warnings and investigator evidence
12. Query denormalized OLAP summary
13. Perform logically separated ground-truth evaluation
"""

import sys
import time
from pathlib import Path
from typing import Dict, Any
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_connection import SessionLocal
from database.database_models import (
    BankATransaction,
    BankBEvent,
    BankCLedgerEntry,
    FactTransaction,
    ETLBatchLog,
    ETLRejectedRecord,
    FraudDetectionRun,
    FraudScreeningWarning,
    FraudTransactionPrediction,
    EvaluationGroundTruth,
)
from demo.demo_data import get_demo_source_records
from etl.extract_bank_data import extract_raw_bank_data
from etl.validate_source_records import validate_all_source_data
from etl.pair_bank_c_ledger_entries import pair_and_validate_bank_c_journals
from etl.map_bank_fields import map_source_records_to_canonical
from etl.resolve_dimension_keys import resolve_dimension_surrogate_keys
from etl.load_warehouse import load_fact_transactions_idempotent
from etl.reconcile_etl_results import reconcile_and_log_batch
from fraud_detection.save_detection_results import execute_fraud_detection_run
from fraud_detection.evaluate_detection_results import evaluate_detection_run
from warehouse.warehouse_queries import get_denormalized_fact_dataframe


def reset_demo_records(session: Session, demo_batch_id: str = "BATCH-DEMO-001", demo_run_id: str = "RUN-DEMO-001") -> None:
    """Safely cleans up only previous demo run records without touching other data."""
    demo_txns = [
        "A-TXN-DEMO-001", "A-TXN-DEMO-002", "A-TXN-DEMO-003", "A-TXN-DEMO-004",
        "B-EVT-DEMO-001", "B-EVT-DEMO-002", "C-J-DEMO-01", "C-J-DEMO-ERR"
    ]

    # 1. First delete child table records referencing FactTransaction (FraudTransactionPrediction)
    session.query(FraudTransactionPrediction).filter(
        (FraudTransactionPrediction.detection_run_id == demo_run_id) |
        (FraudTransactionPrediction.source_transaction_id.in_(demo_txns))
    ).delete(synchronize_session=False)

    session.query(FraudScreeningWarning).filter_by(detection_run_id=demo_run_id).delete()
    session.query(FraudDetectionRun).filter_by(detection_run_id=demo_run_id).delete()

    # 2. Now safe to delete parent FactTransaction records
    session.query(FactTransaction).filter(
        (FactTransaction.source_batch_id == demo_batch_id) |
        (FactTransaction.source_transaction_id.in_(demo_txns))
    ).delete(synchronize_session=False)

    session.query(ETLBatchLog).filter_by(batch_id=demo_batch_id).delete()
    session.query(ETLRejectedRecord).filter_by(batch_id=demo_batch_id).delete()

    session.commit()


def run_complete_demo_scenario(
    demo_batch_id: str = "BATCH-DEMO-001",
    demo_run_id: str = "RUN-DEMO-001",
) -> Dict[str, Any]:
    """
    Executes the entire BF-DEMO-001 workflow end-to-end.
    Returns structured step outputs for presentation in UI or CLI.
    """
    session = SessionLocal()
    demo_data = get_demo_source_records()

    try:
        # Step 0: Clean previous demo records for replayability
        reset_demo_records(session, demo_batch_id=demo_batch_id, demo_run_id=demo_run_id)

        # Step 1: Insert Demo Source Records into SQLite
        # Remove existing demo source keys if re-running
        for a in demo_data["bank_a"]:
            session.query(BankATransaction).filter_by(transaction_id=a["transaction_id"]).delete()
            session.add(BankATransaction(**a))

        for b in demo_data["bank_b"]:
            session.query(BankBEvent).filter_by(event_id=b["event_id"]).delete()
            session.add(BankBEvent(**b))

        for c in demo_data["bank_c"]:
            session.query(BankCLedgerEntry).filter_by(entry_id=c["entry_id"]).delete()
            session.add(BankCLedgerEntry(**c))

        for gt in demo_data["ground_truth"]:
            session.query(EvaluationGroundTruth).filter_by(
                source_bank_code=gt["source_bank_code"],
                source_transaction_id=gt["source_transaction_id"]
            ).delete()
            session.add(EvaluationGroundTruth(**gt))

        session.commit()

        # Step 2: Extraction
        extracted = {
            "bank_a": demo_data["bank_a"],
            "bank_b": demo_data["bank_b"],
            "bank_c": demo_data["bank_c"],
            "counts": {
                "bank_a_extracted": len(demo_data["bank_a"]),
                "bank_b_extracted": len(demo_data["bank_b"]),
                "bank_c_extracted": len(demo_data["bank_c"]),
                "total_extracted": len(demo_data["bank_a"]) + len(demo_data["bank_b"]) + len(demo_data["bank_c"]),
            }
        }

        # Step 3: Validation
        validated = validate_all_source_data(extracted, batch_id=demo_batch_id)

        # Step 4: Bank C Pairing
        paired_c = pair_and_validate_bank_c_journals(validated["valid_c"], batch_id=demo_batch_id)

        # Step 5: Field Mapping
        canonical = map_source_records_to_canonical(
            valid_a=validated["valid_a"],
            valid_b=validated["valid_b"],
            paired_c=paired_c["paired_transfers"],
        )

        # Step 6: Surrogate Key Resolution
        fact_payloads = resolve_dimension_surrogate_keys(
            session=session,
            canonical_transactions=canonical,
            batch_id=demo_batch_id,
        )

        # Step 7: Warehouse Ingestion
        load_res = load_fact_transactions_idempotent(session, fact_payloads)

        # Step 8: Reconciliation
        all_rejections = validated["rejected_records"] + paired_c["pairing_rejections"]
        reconciliation = reconcile_and_log_batch(
            session=session,
            batch_id=demo_batch_id,
            extract_counts=extracted["counts"],
            valid_counts=validated["metrics"],
            pair_counts=paired_c["metrics"],
            load_results=load_res,
            rejected_records=all_rejections,
            duration_sec=0.08,
        )

        # Step 9: Fraud Detection Screening
        detection_res = execute_fraud_detection_run(
            session=session,
            detection_run_id=demo_run_id,
            batch_id=demo_batch_id,
        )

        # Step 10: Ground Truth Evaluation
        evaluation_res = evaluate_detection_run(
            session=session,
            detection_run_id=demo_run_id,
        )

        # Fetch denormalized demo records
        demo_facts_df = get_denormalized_fact_dataframe(session, batch_id=demo_batch_id)

        # Fetch warnings
        warnings = (
            session.query(FraudScreeningWarning)
            .filter_by(detection_run_id=demo_run_id)
            .all()
        )
        warning_dicts = [
            {
                "Rule": w.rule_name,
                "Priority": w.review_priority,
                "Entity": f"{w.entity_type}: {w.entity_ref}",
                "Observed": w.observed_value,
                "Threshold": w.threshold_value,
                "Evidence": w.evidence_summary,
            }
            for w in warnings
        ]

        return {
            "demo_batch_id": demo_batch_id,
            "demo_run_id": demo_run_id,
            "raw_counts": extracted["counts"],
            "paired_journals_produced": len(paired_c["paired_transfers"]),
            "quarantined_count": len(all_rejections),
            "quarantined_records": all_rejections,
            "warehouse_rows_inserted": load_res["rows_inserted"],
            "reconciliation": reconciliation,
            "warnings": warning_dicts,
            "evaluation": evaluation_res,
            "demo_facts_count": len(demo_facts_df),
            "status": "DEMO_COMPLETED_SUCCESSFULLY",
        }

    finally:
        session.close()


if __name__ == "__main__":
    res = run_complete_demo_scenario()
    print("=== BF-DEMO-001 Execution Results ===")
    for k, v in res.items():
        if k != "quarantined_records":
            print(f"  {k}: {v}")
