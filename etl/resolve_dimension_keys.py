"""
BankFusion ETL Stage 5: Dimension Surrogate Key Resolver
========================================================
Resolves natural keys to warehouse surrogate keys across all seven dimensions.

1. What the file does:
   Translates canonical business attributes into integer foreign keys:
   bank_key, date_key, time_key, source_account_key, destination_account_key,
   payment_method_key, status_key, and device_key.
2. Why it exists:
   Enforces Kimball dimensional modeling standards where fact tables join strictly
   on integer surrogate keys rather than variable-length natural business strings.
3. What inputs it accepts:
   - session: Active SQLAlchemy session
   - canonical_transactions: Standardized transaction list from map_bank_fields.py
   - batch_id: Active ETL batch tracking identifier
4. What output it produces:
   List of fact-table dictionaries populated with surrogate keys and audit metadata.
5. Which other files call it:
   Called by etl/run_etl_pipeline.py and test suites.
6. Which DWM concept it demonstrates:
   Surrogate key assignment, slowly changing dimension handling, and conformed dimension joins.
7. How a student can explain it during a viva:
   "Our fact table does not store account strings or bank codes directly. This module resolves
   every natural reference to a surrogate integer key using cached dimension maps, ensuring fast
   joins and indexing in our star schema."
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from warehouse.warehouse_queries import (
    ensure_dim_date,
    resolve_account_key,
    resolve_device_key,
    load_dimension_cache,
)


def resolve_dimension_surrogate_keys(
    session: Session,
    canonical_transactions: List[Dict[str, Any]],
    batch_id: str,
) -> List[Dict[str, Any]]:
    """
    Transforms canonical transaction records into FactTransaction payload dictionaries
    with all 8 dimension foreign keys resolved.
    """
    cache = load_dimension_cache(session)
    now_str = datetime.now().isoformat()
    fact_payloads: List[Dict[str, Any]] = []

    for rec in canonical_transactions:
        # 1. Bank key
        bank_key = cache["banks"][rec["source_bank_code"]]

        # 2. Date and Time keys
        dt = datetime.fromisoformat(rec["transaction_timestamp"])
        date_key = ensure_dim_date(session, dt)
        time_key = dt.hour * 100 + dt.minute

        # 3. Source account key (composite: bank_key + sender_ref)
        src_acc_tuple = (bank_key, rec["sender_account_ref"])
        if src_acc_tuple in cache["accounts"]:
            source_acc_key = cache["accounts"][src_acc_tuple]
        else:
            source_acc_key = resolve_account_key(
                session, bank_key, rec["sender_account_ref"]
            )
            cache["accounts"][src_acc_tuple] = source_acc_key

        # 4. Destination account key (composite: dest_bank_key + receiver_ref)
        dest_bank_code = rec.get("receiver_bank_code") or rec["source_bank_code"]
        dest_bank_key = cache["banks"].get(dest_bank_code, bank_key)
        dest_acc_tuple = (dest_bank_key, rec["receiver_account_ref"])
        if dest_acc_tuple in cache["accounts"]:
            dest_acc_key = cache["accounts"][dest_acc_tuple]
        else:
            dest_acc_key = resolve_account_key(
                session, dest_bank_key, rec["receiver_account_ref"]
            )
            cache["accounts"][dest_acc_tuple] = dest_acc_key

        # 5. Payment method key
        method_key = cache["methods"].get(rec["payment_method"], cache["methods"]["UPI"])

        # 6. Status key
        status_key = cache["statuses"].get(rec["transaction_status"], cache["statuses"]["PENDING"])

        # 7. Device key
        device_token = rec.get("device_token")
        token_str = device_token.strip() if device_token else "UNKNOWN_DEVICE"
        if token_str in cache["devices"]:
            device_key = cache["devices"][token_str]
        else:
            device_key = resolve_device_key(session, device_token)
            cache["devices"][token_str] = device_key

        fact_payloads.append({
            "bank_key": bank_key,
            "date_key": date_key,
            "time_key": time_key,
            "source_account_key": source_acc_key,
            "destination_account_key": dest_acc_key,
            "payment_method_key": method_key,
            "status_key": status_key,
            "device_key": device_key,
            "source_transaction_id": rec["source_transaction_id"],
            "source_record_refs": rec["source_record_refs"],
            "transaction_timestamp": rec["transaction_timestamp"],
            "epoch_timestamp": rec["epoch_timestamp"],
            "amount_paise": rec["amount_paise"],
            "currency": rec["currency"],
            "source_batch_id": batch_id,
            "loaded_at": now_str,
        })

    session.flush()
    return fact_payloads

