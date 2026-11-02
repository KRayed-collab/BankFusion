"""
BankFusion ETL Stage 1: Source Data Extractor
=============================================
Performs read-only extraction of raw records from all three bank source tables.

1. What the file does:
   Connects to SQLite and reads raw records from bank_a_transactions, bank_b_events,
   and bank_c_ledger_entries without modifying source state.
2. Why it exists:
   To decouple extraction from downstream validation and transformation, guaranteeing
   zero side-effects on operational source data.
3. What inputs it accepts:
   - session: Active SQLAlchemy session
   - limit_per_bank: Optional integer to cap extraction size
4. What output it produces:
   Dictionary containing extracted lists of dictionaries for 'bank_a', 'bank_b', and 'bank_c',
   along with extracted row counts.
5. Which other files call it:
   Called by etl/run_etl_pipeline.py and test suites.
6. Which DWM concept it demonstrates:
   The 'E' in ETL—read-only staging extraction from heterogeneous operational stores.
7. How a student can explain it during a viva:
   "Our extractor queries the three independent source tables and extracts them into structured
   Python dictionaries. It is purely read-only and never mutates the underlying source tables."
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_models import (
    BankATransaction,
    BankBEvent,
    BankCLedgerEntry,
)


def extract_raw_bank_data(
    session: Session,
    limit_per_bank: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Extracts raw records from Bank A, Bank B, and Bank C.
    Returns dictionary with raw record lists and extraction metrics.
    """
    query_a = session.query(BankATransaction)
    query_b = session.query(BankBEvent)
    query_c = session.query(BankCLedgerEntry)

    if limit_per_bank:
        query_a = query_a.limit(limit_per_bank)
        query_b = query_b.limit(limit_per_bank)
        query_c = query_c.limit(limit_per_bank)

    records_a = [
        {
            "transaction_id": r.transaction_id,
            "transaction_timestamp": r.transaction_timestamp,
            "sender_account_ref": r.sender_account_ref,
            "receiver_account_ref": r.receiver_account_ref,
            "receiver_bank_code": r.receiver_bank_code,
            "amount_paise": r.amount_paise,
            "payment_mode": r.payment_mode,
            "transaction_status": r.transaction_status,
            "device_token": r.device_token,
        }
        for r in query_a.all()
    ]

    records_b = [
        {
            "event_id": r.event_id,
            "payment_request_ref": r.payment_request_ref,
            "event_timestamp": r.event_timestamp,
            "sender_wallet_ref": r.sender_wallet_ref,
            "beneficiary_account_ref": r.beneficiary_account_ref,
            "beneficiary_bank_code": r.beneficiary_bank_code,
            "value_paise": r.value_paise,
            "channel_code": r.channel_code,
            "result_code": r.result_code,
            "device_token": r.device_token,
        }
        for r in query_b.all()
    ]

    records_c = [
        {
            "entry_id": r.entry_id,
            "journal_id": r.journal_id,
            "posting_timestamp": r.posting_timestamp,
            "ledger_account_ref": r.ledger_account_ref,
            "counterparty_account_ref": r.counterparty_account_ref,
            "counterparty_bank_code": r.counterparty_bank_code,
            "entry_side": r.entry_side,
            "amount_paise": r.amount_paise,
            "currency": r.currency,
            "transfer_type": r.transfer_type,
            "entry_status": r.entry_status,
            "device_token": r.device_token,
        }
        for r in query_c.all()
    ]

    return {
        "bank_a": records_a,
        "bank_b": records_b,
        "bank_c": records_c,
        "counts": {
            "bank_a_extracted": len(records_a),
            "bank_b_extracted": len(records_b),
            "bank_c_extracted": len(records_c),
            "total_extracted": len(records_a) + len(records_b) + len(records_c),
        },
    }

