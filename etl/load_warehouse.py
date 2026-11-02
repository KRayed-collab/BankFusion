"""
BankFusion ETL Stage 6: Idempotent Warehouse Loader
===================================================
Loads resolved transaction payloads into FactTransaction with database-level
idempotency, duplicate detection, and granular monetary tracking.

1. What the file does:
   Checks fact payloads against existing (bank_key, source_transaction_id) records.
   Bulk inserts novel records into warehouse_fact_transaction and safely skips duplicates.
2. Why it exists:
   Enforces idempotency: executing an ETL batch multiple times will never produce duplicate
   fact rows or inflate monetary volumes.
3. What inputs it accepts:
   - session: Active SQLAlchemy session
   - fact_payloads: Output list from resolve_dimension_keys.py
   - status_cache: Dict mapping status_code to status_key
4. What output it produces:
   Dictionary containing:
   - 'rows_inserted': Number of new fact records inserted
   - 'rows_skipped': Number of duplicates skipped
   - 'amount_inserted': Integer paise newly inserted
   - 'amount_skipped': Integer paise skipped as duplicates
   - 'status_breakdown': Status-specific decompositions for inserted and skipped amounts
5. Which other files call it:
   Called by etl/run_etl_pipeline.py and test suites.
6. Which DWM concept it demonstrates:
   ETL idempotency, upsert/conflict prevention, and audit traceability.
7. How a student can explain it during a viva:
   "Our loader checks each record against the fact table's composite unique constraint
   (bank_key, source_transaction_id). If we run the ETL pipeline twice on the same data,
   it inserts 0 rows and reports 100% duplicate skips without throwing errors."
"""

import sys
from pathlib import Path
from typing import Dict, List, Any
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_models import FactTransaction, DimTransactionStatus


def load_fact_transactions_idempotent(
    session: Session,
    fact_payloads: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Idempotently loads fact records into warehouse_fact_transaction.
    Detects and skips existing records matching (bank_key, source_transaction_id).
    """
    if not fact_payloads:
        return {
            "rows_inserted": 0,
            "rows_skipped": 0,
            "amount_inserted": 0,
            "amount_skipped": 0,
            "status_inserted": {"SUCCESS": 0, "FAILED": 0, "PENDING": 0},
            "status_skipped": {"SUCCESS": 0, "FAILED": 0, "PENDING": 0},
        }

    # Fetch status keys for status breakdown
    status_map = {
        s.status_key: s.status_code
        for s in session.query(DimTransactionStatus).all()
    }

    # Fetch all existing (bank_key, source_transaction_id) pairs currently in warehouse
    existing_pairs = set(
        session.query(
            FactTransaction.bank_key,
            FactTransaction.source_transaction_id,
        ).all()
    )

    new_payloads: List[Dict[str, Any]] = []
    skipped_payloads: List[Dict[str, Any]] = []

    for p in fact_payloads:
        pair = (p["bank_key"], p["source_transaction_id"])
        if pair in existing_pairs:
            skipped_payloads.append(p)
        else:
            new_payloads.append(p)
            existing_pairs.add(pair)  # Prevent internal batch duplicate collisions

    # Bulk insert new records
    if new_payloads:
        fact_objects = [FactTransaction(**p) for p in new_payloads]
        session.bulk_save_objects(fact_objects)
        session.flush()

    # Calculate status-specific monetary sums
    status_inserted = {"SUCCESS": 0, "FAILED": 0, "PENDING": 0}
    for p in new_payloads:
        code = status_map.get(p["status_key"], "PENDING")
        status_inserted[code] = status_inserted.get(code, 0) + p["amount_paise"]

    status_skipped = {"SUCCESS": 0, "FAILED": 0, "PENDING": 0}
    for p in skipped_payloads:
        code = status_map.get(p["status_key"], "PENDING")
        status_skipped[code] = status_skipped.get(code, 0) + p["amount_paise"]

    return {
        "rows_inserted": len(new_payloads),
        "rows_skipped": len(skipped_payloads),
        "amount_inserted": sum(p["amount_paise"] for p in new_payloads),
        "amount_skipped": sum(p["amount_paise"] for p in skipped_payloads),
        "status_inserted": status_inserted,
        "status_skipped": status_skipped,
    }

