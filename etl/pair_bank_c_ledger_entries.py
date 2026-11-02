"""
BankFusion ETL Stage 3: Bank C Double-Entry Pairing Engine
==========================================================
Reconciles grain disparity for Bank C by grouping and pairing reciprocal
DEBIT and CREDIT ledger entries into unified business transfers.

1. What the file does:
   Groups Bank C entries by journal_id, validates that each journal consists of exactly
   one DEBIT and one CREDIT leg in POSTED status with matching amounts and reciprocal
   counterparty references, and emits one normalized transfer per valid journal.
2. Why it exists:
   Solves the classic DWM grain mismatch problem: Bank C records 2 rows per business transfer,
   whereas Banks A and B record 1 row per attempt.
3. What inputs it accepts:
   - valid_c_entries: Pre-validated Bank C ledger entries
   - batch_id: Current ETL batch identifier
4. What output it produces:
   Dictionary containing:
   - 'paired_journals': List of normalized transfer dicts (1 per valid journal)
   - 'pairing_rejections': Quarantine records for malformed/unbalanced journals
   - 'metrics': Total entries processed, valid journals produced, entries quarantined
5. Which other files call it:
   Called by etl/run_etl_pipeline.py and test suites.
6. Which DWM concept it demonstrates:
   Grain transformation (N:1 reduction), double-entry ledger balancing, and dual lineage preservation.
7. How a student can explain it during a viva:
   "TrustLine Bank stores transfers as separate debit and credit legs under a journal_id.
   Our pairing module groups entries by journal_id, asserts that debit.amount equals credit.amount,
   confirms both accounts reciprocally match, and outputs exactly one warehouse fact row with
   both entry IDs preserved in source_record_refs."
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def pair_and_validate_bank_c_journals(
    valid_c_entries: List[Dict[str, Any]],
    batch_id: str,
) -> Dict[str, Any]:
    """
    Pairs Bank C debit and credit legs by journal_id.
    Produces 1 normalized transfer per valid balanced journal.
    Quarantines unbalanced or unposted journals.
    """
    paired_transfers: List[Dict[str, Any]] = []
    pairing_rejections: List[Dict[str, Any]] = []

    # Group entries by journal_id
    journal_groups: Dict[str, List[Dict[str, Any]]] = {}
    for entry in valid_c_entries:
        j_id = entry["journal_id"]
        journal_groups.setdefault(j_id, []).append(entry)

    now_str = datetime.now().isoformat()

    valid_entries_count = 0
    rejected_entries_count = 0

    for journal_id, legs in journal_groups.items():
        # Condition 1: Must have exactly 2 legs
        if len(legs) != 2:
            reason = f"INVALID_LEG_COUNT_EXPECTED_2_GOT_{len(legs)}"
            for leg in legs:
                pairing_rejections.append({
                    "batch_id": batch_id,
                    "source_bank_code": "BANK_C",
                    "source_record_id": leg.get("entry_id", journal_id),
                    "rejection_stage": "PAIRING",
                    "rejection_reason": reason,
                    "raw_payload": json.dumps(leg),
                    "recorded_at": now_str,
                })
            rejected_entries_count += len(legs)
            continue

        debit_legs = [l for l in legs if l["entry_side"] == "DEBIT"]
        credit_legs = [l for l in legs if l["entry_side"] == "CREDIT"]

        # Condition 2: Exactly 1 DEBIT and 1 CREDIT
        if len(debit_legs) != 1 or len(credit_legs) != 1:
            reason = "UNBALANCED_LEGS_MUST_HAVE_EXACTLY_ONE_DEBIT_AND_ONE_CREDIT"
            for leg in legs:
                pairing_rejections.append({
                    "batch_id": batch_id,
                    "source_bank_code": "BANK_C",
                    "source_record_id": leg["entry_id"],
                    "rejection_stage": "PAIRING",
                    "rejection_reason": reason,
                    "raw_payload": json.dumps(leg),
                    "recorded_at": now_str,
                })
            rejected_entries_count += 2
            continue

        deb = debit_legs[0]
        crd = credit_legs[0]

        # Condition 3: Amounts must match
        if deb["amount_paise"] != crd["amount_paise"]:
            reason = f"MISMATCHED_AMOUNTS_DEBIT_{deb['amount_paise']}_CREDIT_{crd['amount_paise']}"
            for leg in legs:
                pairing_rejections.append({
                    "batch_id": batch_id,
                    "source_bank_code": "BANK_C",
                    "source_record_id": leg["entry_id"],
                    "rejection_stage": "PAIRING",
                    "rejection_reason": reason,
                    "raw_payload": json.dumps(leg),
                    "recorded_at": now_str,
                })
            rejected_entries_count += 2
            continue

        # Condition 4: Both legs must be POSTED
        if deb.get("entry_status") != "POSTED" or crd.get("entry_status") != "POSTED":
            reason = f"UNPOSTED_JOURNAL_STATUS_DEBIT_{deb.get('entry_status')}_CREDIT_{crd.get('entry_status')}"
            for leg in legs:
                pairing_rejections.append({
                    "batch_id": batch_id,
                    "source_bank_code": "BANK_C",
                    "source_record_id": leg["entry_id"],
                    "rejection_stage": "PAIRING",
                    "rejection_reason": reason,
                    "raw_payload": json.dumps(leg),
                    "recorded_at": now_str,
                })
            rejected_entries_count += 2
            continue

        # Condition 5: Reciprocal counterparty references
        reciprocal_ok = (
            deb["counterparty_account_ref"] == crd["ledger_account_ref"]
            and crd["counterparty_account_ref"] == deb["ledger_account_ref"]
        )
        if not reciprocal_ok:
            reason = "NON_RECIPROCAL_COUNTERPARTY_REFERENCES"
            for leg in legs:
                pairing_rejections.append({
                    "batch_id": batch_id,
                    "source_bank_code": "BANK_C",
                    "source_record_id": leg["entry_id"],
                    "rejection_stage": "PAIRING",
                    "rejection_reason": reason,
                    "raw_payload": json.dumps(leg),
                    "recorded_at": now_str,
                })
            rejected_entries_count += 2
            continue

        # Valid Pair: Emit 1 normalized business transfer
        valid_entries_count += 2
        source_record_refs = f"{deb['entry_id']},{crd['entry_id']}"
        paired_transfers.append({
            "journal_id": journal_id,
            "source_record_refs": source_record_refs,
            "transaction_timestamp": deb["posting_timestamp"],
            "sender_account_ref": deb["ledger_account_ref"],
            "receiver_account_ref": crd["ledger_account_ref"],
            "receiver_bank_code": "BANK_C",
            "amount_paise": deb["amount_paise"],
            "payment_mode": deb.get("transfer_type", "BOOK_TRANSFER"),
            "transaction_status": "SUCCESS",  # Valid posted transfer
            "device_token": deb.get("device_token") or crd.get("device_token"),
        })

    return {
        "paired_transfers": paired_transfers,
        "pairing_rejections": pairing_rejections,
        "metrics": {
            "bank_c_valid_entries": valid_entries_count,
            "bank_c_rejected_entries": rejected_entries_count,
            "bank_c_valid_journals": len(paired_transfers),
        },
    }

