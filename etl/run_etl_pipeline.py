"""
BankFusion Master ETL Pipeline Orchestrator
===========================================
Executes the full end-to-end 7-stage ETL pipeline:
Extract -> Validate -> Bank C Pair -> Map -> Resolve Dimensions -> Idempotent Load -> Reconcile.

1. What the file does:
   Coordinates the execution of all ETL pipeline stages in a single transactional workflow,
   producing audit logs, quarantined records, and populated warehouse facts.
2. Why it exists:
   Provides a single repeatable entrypoint called by CLI, tests, Demo Mode, and Streamlit.
3. What inputs it accepts:
   - batch_id: Optional string identifier (auto-generated if omitted)
   - limit_per_bank: Optional cap on records extracted
4. What output it produces:
   Reconciliation summary dictionary reflecting row and monetary balances.
5. Which other files call it:
   Called by demo runner, test suites, and Streamlit Page 2.
6. Which DWM concept it demonstrates:
   End-to-end ETL orchestration, batch pipeline execution, and transaction control.
7. How a student can explain it during a viva:
   "This orchestrator runs our complete 7-stage ETL process. It extracts from the three bank tables,
   validates schemas, pairs Bank C journals, maps fields into canonical format, resolves surrogate keys,
   inserts into FactTransaction with duplicate prevention, and logs audit reconciliation."
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_connection import SessionLocal
from etl.extract_bank_data import extract_raw_bank_data
from etl.validate_source_records import validate_all_source_data
from etl.pair_bank_c_ledger_entries import pair_and_validate_bank_c_journals
from etl.map_bank_fields import map_source_records_to_canonical
from etl.resolve_dimension_keys import resolve_dimension_surrogate_keys
from etl.load_warehouse import load_fact_transactions_idempotent
from etl.reconcile_etl_results import reconcile_and_log_batch


def execute_full_etl_pipeline(
    batch_id: Optional[str] = None,
    limit_per_bank: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Executes the 7-stage ETL pipeline from source tables to warehouse.
    Returns reconciliation summary dictionary.
    """
    if not batch_id:
        timestamp_slug = datetime.now().strftime("%Y%m%d-%H%M%S")
        batch_id = f"BATCH-{timestamp_slug}"

    start_time = time.time()
    session = SessionLocal()

    try:
        # Stage 1: Extract
        extracted = extract_raw_bank_data(session, limit_per_bank=limit_per_bank)
        extract_counts = extracted["counts"]

        # Stage 2: Validate
        validated = validate_all_source_data(extracted, batch_id=batch_id)
        valid_a = validated["valid_a"]
        valid_b = validated["valid_b"]
        valid_c_raw = validated["valid_c"]
        validation_rejections = validated["rejected_records"]
        valid_counts = validated["metrics"]

        # Stage 3: Bank C Debit-Credit Pairing & Reciprocal Validation
        paired_c_result = pair_and_validate_bank_c_journals(valid_c_raw, batch_id=batch_id)
        paired_c_transfers = paired_c_result["paired_transfers"]
        pairing_rejections = paired_c_result["pairing_rejections"]
        pair_counts = paired_c_result["metrics"]

        # Combine all quarantine records
        all_rejected_records = validation_rejections + pairing_rejections

        # Stage 4: Map to Canonical Enums & Fields
        canonical_txns = map_source_records_to_canonical(
            valid_a=valid_a,
            valid_b=valid_b,
            paired_c=paired_c_transfers,
        )

        # Stage 5: Resolve Dimension Surrogate Keys
        fact_payloads = resolve_dimension_surrogate_keys(
            session=session,
            canonical_transactions=canonical_txns,
            batch_id=batch_id,
        )

        # Stage 6: Idempotent Warehouse Load
        load_results = load_fact_transactions_idempotent(
            session=session,
            fact_payloads=fact_payloads,
        )

        # Stage 7: Reconcile and Log
        duration_sec = round(time.time() - start_time, 3)
        reconcile_summary = reconcile_and_log_batch(
            session=session,
            batch_id=batch_id,
            extract_counts=extract_counts,
            valid_counts=valid_counts,
            pair_counts=pair_counts,
            load_results=load_results,
            rejected_records=all_rejected_records,
            duration_sec=duration_sec,
        )

        return reconcile_summary

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Execute BankFusion ETL Pipeline")
    parser.add_argument("--batch-id", type=str, default=None, help="Custom ETL batch identifier")
    args = parser.parse_args()

    result = execute_full_etl_pipeline(batch_id=args.batch_id)
    print("\n=== BankFusion ETL Pipeline Completed ===")
    for k, v in result.items():
        print(f"  {k}: {v}")

