"""
BankFusion ETL Stage 2: Source Data Validator
=============================================
Validates source records against schema constraints, positive monetary ranges,
valid ISO-8601 timestamps, and recognizable status codes. Quarantines invalid records.

1. What the file does:
   Applies business and integrity validation rules to extracted records. Splits records
   into valid sets and quarantine sets with explicit failure reasons.
2. Why it exists:
   Prevents corrupted, negative-amount, or malformed transactions from entering the warehouse,
   recording rejections in etl_rejected_record for auditability.
3. What inputs it accepts:
   - extracted_data: Dictionary output from extract_bank_data.py
   - batch_id: Current ETL batch tracking identifier
4. What output it produces:
   Dictionary containing:
   - 'valid_a', 'valid_b', 'valid_c': Clean records
   - 'rejected_records': List of quarantine dicts ready for insertion into etl_rejected_record
   - 'validation_metrics': Counts of valid and rejected rows per bank
5. Which other files call it:
   Called by etl/run_etl_pipeline.py and test suites.
6. Which DWM concept it demonstrates:
   Data Quality Assurance (DQA), rejection quarantine, and auditability.
7. How a student can explain it during a viva:
   "Our validation layer inspects incoming data before any transformation occurs. If a record has
   a negative amount, invalid timestamp, or missing account, it is quarantined in etl_rejected_record
   with the exact rejection reason."
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def validate_timestamp_iso(ts_str: str) -> bool:
    """Validates that a timestamp conforms to ISO-8601 format."""
    try:
        datetime.fromisoformat(ts_str)
        return True
    except (ValueError, TypeError):
        return False


def validate_bank_a_record(rec: Dict[str, Any]) -> Tuple[bool, str]:
    """Validates a single Bank A transaction record."""
    if not rec.get("transaction_id"):
        return False, "MISSING_TRANSACTION_ID"
    if not validate_timestamp_iso(rec.get("transaction_timestamp", "")):
        return False, "INVALID_TIMESTAMP_FORMAT"
    if not rec.get("sender_account_ref"):
        return False, "MISSING_SENDER_ACCOUNT"
    if not rec.get("receiver_account_ref"):
        return False, "MISSING_RECEIVER_ACCOUNT"
    if not isinstance(rec.get("amount_paise"), int) or rec["amount_paise"] <= 0:
        return False, "INVALID_AMOUNT_MUST_BE_POSITIVE_INTEGER_PAISE"
    if rec.get("transaction_status") not in ["SUCCESS", "FAILED", "PENDING"]:
        return False, f"UNRECOGNIZED_TRANSACTION_STATUS_{rec.get('transaction_status')}"
    return True, "VALID"


def validate_bank_b_record(rec: Dict[str, Any]) -> Tuple[bool, str]:
    """Validates a single Bank B event record."""
    if not rec.get("event_id"):
        return False, "MISSING_EVENT_ID"
    if not rec.get("payment_request_ref"):
        return False, "MISSING_PAYMENT_REQUEST_REF"
    if not validate_timestamp_iso(rec.get("event_timestamp", "")):
        return False, "INVALID_TIMESTAMP_FORMAT"
    if not rec.get("sender_wallet_ref"):
        return False, "MISSING_SENDER_WALLET"
    if not rec.get("beneficiary_account_ref"):
        return False, "MISSING_BENEFICIARY_ACCOUNT"
    if not isinstance(rec.get("value_paise"), int) or rec["value_paise"] <= 0:
        return False, "INVALID_VALUE_MUST_BE_POSITIVE_INTEGER_PAISE"
    if rec.get("result_code") not in ["RC_00_SUCCESS", "RC_05_FAILED", "RC_99_PENDING"]:
        return False, f"UNRECOGNIZED_RESULT_CODE_{rec.get('result_code')}"
    return True, "VALID"


def validate_bank_c_entry(rec: Dict[str, Any]) -> Tuple[bool, str]:
    """Validates a single Bank C ledger entry for baseline field integrity."""
    if not rec.get("entry_id"):
        return False, "MISSING_ENTRY_ID"
    if not rec.get("journal_id"):
        return False, "MISSING_JOURNAL_ID"
    if not validate_timestamp_iso(rec.get("posting_timestamp", "")):
        return False, "INVALID_TIMESTAMP_FORMAT"
    if not rec.get("ledger_account_ref"):
        return False, "MISSING_LEDGER_ACCOUNT"
    if rec.get("entry_side") not in ["DEBIT", "CREDIT"]:
        return False, "INVALID_ENTRY_SIDE_MUST_BE_DEBIT_OR_CREDIT"
    if not isinstance(rec.get("amount_paise"), int) or rec["amount_paise"] <= 0:
        return False, "INVALID_AMOUNT_MUST_BE_POSITIVE_INTEGER_PAISE"
    return True, "VALID"


def validate_all_source_data(
    extracted_data: Dict[str, Any],
    batch_id: str,
) -> Dict[str, Any]:
    """
    Validates records across all three banks.
    Returns clean records, rejection entries, and validation counters.
    """
    valid_a: List[Dict[str, Any]] = []
    valid_b: List[Dict[str, Any]] = []
    valid_c: List[Dict[str, Any]] = []
    rejected_records: List[Dict[str, Any]] = []

    now_str = datetime.now().isoformat()

    # 1. Validate Bank A
    for rec in extracted_data["bank_a"]:
        is_valid, reason = validate_bank_a_record(rec)
        if is_valid:
            valid_a.append(rec)
        else:
            rejected_records.append({
                "batch_id": batch_id,
                "source_bank_code": "BANK_A",
                "source_record_id": rec.get("transaction_id", "UNKNOWN"),
                "rejection_stage": "VALIDATE",
                "rejection_reason": reason,
                "raw_payload": json.dumps(rec),
                "recorded_at": now_str,
            })

    # 2. Validate Bank B
    for rec in extracted_data["bank_b"]:
        is_valid, reason = validate_bank_b_record(rec)
        if is_valid:
            valid_b.append(rec)
        else:
            rejected_records.append({
                "batch_id": batch_id,
                "source_bank_code": "BANK_B",
                "source_record_id": rec.get("event_id", "UNKNOWN"),
                "rejection_stage": "VALIDATE",
                "rejection_reason": reason,
                "raw_payload": json.dumps(rec),
                "recorded_at": now_str,
            })

    # 3. Validate Bank C initial entry schema
    for rec in extracted_data["bank_c"]:
        is_valid, reason = validate_bank_c_entry(rec)
        if is_valid:
            valid_c.append(rec)
        else:
            rejected_records.append({
                "batch_id": batch_id,
                "source_bank_code": "BANK_C",
                "source_record_id": rec.get("entry_id", "UNKNOWN"),
                "rejection_stage": "VALIDATE",
                "rejection_reason": reason,
                "raw_payload": json.dumps(rec),
                "recorded_at": now_str,
            })

    return {
        "valid_a": valid_a,
        "valid_b": valid_b,
        "valid_c": valid_c,
        "rejected_records": rejected_records,
        "metrics": {
            "bank_a_valid": len(valid_a),
            "bank_a_rejected": len(extracted_data["bank_a"]) - len(valid_a),
            "bank_b_valid": len(valid_b),
            "bank_b_rejected": len(extracted_data["bank_b"]) - len(valid_b),
            "bank_c_valid": len(valid_c),
            "bank_c_rejected": len(extracted_data["bank_c"]) - len(valid_c),
        },
    }

