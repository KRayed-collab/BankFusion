"""
BankFusion ETL Stage 4: Field Mapping & Standardization Engine
==============================================================
Maps heterogeneous source fields and status codes from Banks A, B, and C
into a standardized canonical transaction dictionary.

1. What the file does:
   Applies declarative configuration mappings from config/bank_field_mapping.json.
   Transforms bank-specific terminology (e.g., Bank B 'value_paise' and 'RC_00_SUCCESS')
   into canonical warehouse attributes ('amount_paise', 'SUCCESS').
2. Why it exists:
   Insulates the data warehouse fact model from operational system idiosyncrasies
   and allows declarative schema evolution.
3. What inputs it accepts:
   - valid_a: Valid Bank A records
   - valid_b: Valid Bank B records
   - paired_c: Valid paired Bank C transfers
4. What output it produces:
   List of standardized canonical transaction dictionaries ready for dimension resolution.
5. Which other files call it:
   Called by etl/run_etl_pipeline.py and test suites.
6. Which DWM concept it demonstrates:
   Schema integration, semantic mapping, and domain code standardization.
7. How a student can explain it during a viva:
   "Each bank uses different column names—Bank A calls it amount_inr, Bank B calls it value,
   Bank B uses result codes like RC_00_SUCCESS, while Bank A uses transaction_status.
   Our mapping layer normalizes these into canonical concepts like amount_paise and SUCCESS."
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.path_resolver import get_config_path

CONFIG_PATH = get_config_path("bank_field_mapping.json")


def load_mapping_config() -> Dict[str, Any]:
    """Loads declarative field mapping rules from JSON."""
    cfg_file = get_config_path("bank_field_mapping.json")
    with open(cfg_file, "r", encoding="utf-8") as f:
        return json.load(f)


def map_source_records_to_canonical(
    valid_a: List[Dict[str, Any]],
    valid_b: List[Dict[str, Any]],
    paired_c: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Standardizes valid records from all three banks into a uniform list
    of canonical transaction dictionaries.
    """
    config = load_mapping_config()
    canonical_transactions: List[Dict[str, Any]] = []

    # 1. Map Bank A
    map_a = config["BANK_A"]
    for rec in valid_a:
        dt = datetime.fromisoformat(rec["transaction_timestamp"])
        epoch = int(dt.timestamp())
        status = map_a["status_mapping"].get(rec["transaction_status"], "PENDING")
        method = map_a["method_mapping"].get(rec["payment_mode"], "UPI")

        canonical_transactions.append({
            "source_transaction_id": rec["transaction_id"],
            "source_record_refs": rec["transaction_id"],
            "source_bank_code": "BANK_A",
            "transaction_timestamp": rec["transaction_timestamp"],
            "epoch_timestamp": epoch,
            "sender_account_ref": rec["sender_account_ref"],
            "receiver_account_ref": rec["receiver_account_ref"],
            "receiver_bank_code": rec["receiver_bank_code"],
            "amount_paise": rec["amount_paise"],
            "currency": "INR",
            "payment_method": method,
            "transaction_status": status,
            "device_token": rec.get("device_token"),
        })

    # 2. Map Bank B
    map_b = config["BANK_B"]
    for rec in valid_b:
        dt = datetime.fromisoformat(rec["event_timestamp"])
        epoch = int(dt.timestamp())
        status = map_b["status_mapping"].get(rec["result_code"], "FAILED")
        method = map_b["method_mapping"].get(rec["channel_code"], "WALLET")

        canonical_transactions.append({
            "source_transaction_id": rec["event_id"],
            "source_record_refs": rec["event_id"],
            "source_bank_code": "BANK_B",
            "transaction_timestamp": rec["event_timestamp"],
            "epoch_timestamp": epoch,
            "sender_account_ref": rec["sender_wallet_ref"],
            "receiver_account_ref": rec["beneficiary_account_ref"],
            "receiver_bank_code": rec["beneficiary_bank_code"],
            "amount_paise": rec["value_paise"],
            "currency": "INR",
            "payment_method": method,
            "transaction_status": status,
            "device_token": rec.get("device_token"),
        })

    # 3. Map Bank C (paired transfers)
    map_c = config["BANK_C"]
    for rec in paired_c:
        dt = datetime.fromisoformat(rec["transaction_timestamp"])
        epoch = int(dt.timestamp())
        status = map_c["status_mapping"].get(rec["transaction_status"], "SUCCESS")
        method = map_c["method_mapping"].get(rec["payment_mode"], "BOOK_TRANSFER")

        canonical_transactions.append({
            "source_transaction_id": rec["journal_id"],
            "source_record_refs": rec["source_record_refs"],
            "source_bank_code": "BANK_C",
            "transaction_timestamp": rec["transaction_timestamp"],
            "epoch_timestamp": epoch,
            "sender_account_ref": rec["sender_account_ref"],
            "receiver_account_ref": rec["receiver_account_ref"],
            "receiver_bank_code": rec["receiver_bank_code"],
            "amount_paise": rec["amount_paise"],
            "currency": "INR",
            "payment_method": method,
            "transaction_status": status,
            "device_token": rec.get("device_token"),
        })

    return canonical_transactions

