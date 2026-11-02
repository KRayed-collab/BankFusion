"""
BankFusion Predefined Demonstration Dataset (BF-DEMO-001)
=========================================================
Contains deterministic raw records across Banks A, B, and C specifically crafted
for the practical viva examination walkthrough.

Scenario Elements:
1. Bank A: Velocity burst (4 rapid attempts in 150 seconds by A-ACC-DEMO-01).
2. Bank B: Wallet event retry lifecycle (Request B-REQ-DEMO-01: 1 failure + 1 success).
3. Bank C: Balanced double-entry book transfer (C-J-DEMO-01) + 1 malformed journal (C-J-DEMO-ERR)
   with mismatched debit/credit amounts to demonstrate ETL quarantine.
4. Shared Device: Hardware token SIM-DEVICE-DEMO-SHARED multiplexed across 3 banks.
5. Ground Truth: Pre-labeled records for post-detection validation.
"""

from typing import Dict, List, Any


def get_demo_source_records() -> Dict[str, Any]:
    """Returns the raw source dictionaries for the BF-DEMO-001 scenario."""

    bank_a_records = [
        # Velocity burst attempt 1
        {
            "transaction_id": "A-TXN-DEMO-001",
            "transaction_timestamp": "2026-11-01T15:00:10+05:30",
            "sender_account_ref": "A-ACC-DEMO-01",
            "receiver_account_ref": "B-ACC-DEMO-02",
            "receiver_bank_code": "BANK_B",
            "amount_paise": 500000,  # ₹5,000
            "payment_mode": "UPI",
            "transaction_status": "SUCCESS",
            "device_token": "SIM-DEVICE-DEMO-SHARED",
        },
        # Velocity burst attempt 2 (Failed attempt 30s later)
        {
            "transaction_id": "A-TXN-DEMO-002",
            "transaction_timestamp": "2026-11-01T15:00:40+05:30",
            "sender_account_ref": "A-ACC-DEMO-01",
            "receiver_account_ref": "B-ACC-DEMO-02",
            "receiver_bank_code": "BANK_B",
            "amount_paise": 500000,
            "payment_mode": "UPI",
            "transaction_status": "FAILED",
            "device_token": "SIM-DEVICE-DEMO-SHARED",
        },
        # Velocity burst attempt 3 (Failed attempt 40s later)
        {
            "transaction_id": "A-TXN-DEMO-003",
            "transaction_timestamp": "2026-11-01T15:01:20+05:30",
            "sender_account_ref": "A-ACC-DEMO-01",
            "receiver_account_ref": "B-ACC-DEMO-02",
            "receiver_bank_code": "BANK_B",
            "amount_paise": 500000,
            "payment_mode": "UPI",
            "transaction_status": "FAILED",
            "device_token": "SIM-DEVICE-DEMO-SHARED",
        },
        # Velocity burst attempt 4 (Successful attempt 40s later -> Total: 4 attempts in 110s)
        {
            "transaction_id": "A-TXN-DEMO-004",
            "transaction_timestamp": "2026-11-01T15:02:00+05:30",
            "sender_account_ref": "A-ACC-DEMO-01",
            "receiver_account_ref": "B-ACC-DEMO-02",
            "receiver_bank_code": "BANK_B",
            "amount_paise": 500000,
            "payment_mode": "UPI",
            "transaction_status": "SUCCESS",
            "device_token": "SIM-DEVICE-DEMO-SHARED",
        },
    ]

    bank_b_records = [
        # Event 1: Failed attempt on payment request B-REQ-DEMO-01
        {
            "event_id": "B-EVT-DEMO-001",
            "payment_request_ref": "B-REQ-DEMO-01",
            "event_timestamp": "2026-11-01T15:10:00+05:30",
            "sender_wallet_ref": "B-ACC-DEMO-02",
            "beneficiary_account_ref": "C-ACC-DEMO-03",
            "beneficiary_bank_code": "BANK_C",
            "value_paise": 750000,  # ₹7,500
            "channel_code": "WALLET_TRANSFER",
            "result_code": "RC_05_FAILED",
            "device_token": "SIM-DEVICE-DEMO-SHARED",
        },
        # Event 2: Successful retry 25 seconds later
        {
            "event_id": "B-EVT-DEMO-002",
            "payment_request_ref": "B-REQ-DEMO-01",
            "event_timestamp": "2026-11-01T15:10:25+05:30",
            "sender_wallet_ref": "B-ACC-DEMO-02",
            "beneficiary_account_ref": "C-ACC-DEMO-03",
            "beneficiary_bank_code": "BANK_C",
            "value_paise": 750000,
            "channel_code": "WALLET_TRANSFER",
            "result_code": "RC_00_SUCCESS",
            "device_token": "SIM-DEVICE-DEMO-SHARED",
        },
    ]

    bank_c_records = [
        # Journal 1 (Valid Balanced Internal Transfer)
        # DEBIT leg (Sender: C-ACC-DEMO-03)
        {
            "entry_id": "C-E-DEMO-001",
            "journal_id": "C-J-DEMO-01",
            "posting_timestamp": "2026-11-01T15:20:00+05:30",
            "ledger_account_ref": "C-ACC-DEMO-03",
            "counterparty_account_ref": "C-ACC-DEMO-04",
            "counterparty_bank_code": "BANK_C",
            "entry_side": "DEBIT",
            "amount_paise": 1000000,  # ₹10,000
            "currency": "INR",
            "transfer_type": "BOOK_TRANSFER",
            "entry_status": "POSTED",
            "device_token": "SIM-DEVICE-DEMO-SHARED",
        },
        # CREDIT leg (Receiver: C-ACC-DEMO-04)
        {
            "entry_id": "C-E-DEMO-002",
            "journal_id": "C-J-DEMO-01",
            "posting_timestamp": "2026-11-01T15:20:00+05:30",
            "ledger_account_ref": "C-ACC-DEMO-04",
            "counterparty_account_ref": "C-ACC-DEMO-03",
            "counterparty_bank_code": "BANK_C",
            "entry_side": "CREDIT",
            "amount_paise": 1000000,
            "currency": "INR",
            "transfer_type": "BOOK_TRANSFER",
            "entry_status": "POSTED",
            "device_token": "SIM-DEVICE-DEMO-SHARED",
        },
        # Journal 2 (Malformed Test Case for Quarantine Demonstration)
        # Mismatched amounts: Debit 300,000 paise vs Credit 250,000 paise
        {
            "entry_id": "C-E-DEMO-ERR1",
            "journal_id": "C-J-DEMO-ERR",
            "posting_timestamp": "2026-11-01T15:30:00+05:30",
            "ledger_account_ref": "C-ACC-DEMO-05",
            "counterparty_account_ref": "C-ACC-DEMO-06",
            "counterparty_bank_code": "BANK_C",
            "entry_side": "DEBIT",
            "amount_paise": 300000,  # ₹3,000
            "currency": "INR",
            "transfer_type": "BOOK_TRANSFER",
            "entry_status": "POSTED",
            "device_token": "SIM-DEVICE-DEMO-05",
        },
        {
            "entry_id": "C-E-DEMO-ERR2",
            "journal_id": "C-J-DEMO-ERR",
            "posting_timestamp": "2026-11-01T15:30:00+05:30",
            "ledger_account_ref": "C-ACC-DEMO-06",
            "counterparty_account_ref": "C-ACC-DEMO-05",
            "counterparty_bank_code": "BANK_C",
            "entry_side": "CREDIT",
            "amount_paise": 250000,  # ₹2,500 (MISMATCH!)
            "currency": "INR",
            "transfer_type": "BOOK_TRANSFER",
            "entry_status": "POSTED",
            "device_token": "SIM-DEVICE-DEMO-05",
        },
    ]

    ground_truth_labels = [
        # Bank A velocity burst records (Suspicious)
        {"scenario_type": "VELOCITY_BURST", "source_bank_code": "BANK_A", "source_transaction_id": "A-TXN-DEMO-001", "source_record_refs": "A-TXN-DEMO-001", "account_ref": "A-ACC-DEMO-01", "device_token": "SIM-DEVICE-DEMO-SHARED", "is_suspicious": 1, "notes": "Demo Velocity Burst Txn 1"},
        {"scenario_type": "VELOCITY_BURST", "source_bank_code": "BANK_A", "source_transaction_id": "A-TXN-DEMO-002", "source_record_refs": "A-TXN-DEMO-002", "account_ref": "A-ACC-DEMO-01", "device_token": "SIM-DEVICE-DEMO-SHARED", "is_suspicious": 1, "notes": "Demo Velocity Burst Txn 2 (Failed)"},
        {"scenario_type": "VELOCITY_BURST", "source_bank_code": "BANK_A", "source_transaction_id": "A-TXN-DEMO-003", "source_record_refs": "A-TXN-DEMO-003", "account_ref": "A-ACC-DEMO-01", "device_token": "SIM-DEVICE-DEMO-SHARED", "is_suspicious": 1, "notes": "Demo Velocity Burst Txn 3 (Failed)"},
        {"scenario_type": "VELOCITY_BURST", "source_bank_code": "BANK_A", "source_transaction_id": "A-TXN-DEMO-004", "source_record_refs": "A-TXN-DEMO-004", "account_ref": "A-ACC-DEMO-01", "device_token": "SIM-DEVICE-DEMO-SHARED", "is_suspicious": 1, "notes": "Demo Velocity Burst Txn 4"},
        # Bank B events (Shared device farm)
        {"scenario_type": "SHARED_DEVICE_FARM", "source_bank_code": "BANK_B", "source_transaction_id": "B-EVT-DEMO-001", "source_record_refs": "B-EVT-DEMO-001", "account_ref": "B-ACC-DEMO-02", "device_token": "SIM-DEVICE-DEMO-SHARED", "is_suspicious": 1, "notes": "Demo Shared Device on Bank B"},
        {"scenario_type": "SHARED_DEVICE_FARM", "source_bank_code": "BANK_B", "source_transaction_id": "B-EVT-DEMO-002", "source_record_refs": "B-EVT-DEMO-002", "account_ref": "B-ACC-DEMO-02", "device_token": "SIM-DEVICE-DEMO-SHARED", "is_suspicious": 1, "notes": "Demo Shared Device on Bank B Retry"},
        # Bank C valid journal (Shared device farm)
        {"scenario_type": "SHARED_DEVICE_FARM", "source_bank_code": "BANK_C", "source_transaction_id": "C-J-DEMO-01", "source_record_refs": "C-E-DEMO-001,C-E-DEMO-002", "account_ref": "C-ACC-DEMO-03", "device_token": "SIM-DEVICE-DEMO-SHARED", "is_suspicious": 1, "notes": "Demo Shared Device on Bank C"},
    ]

    return {
        "bank_a": bank_a_records,
        "bank_b": bank_b_records,
        "bank_c": bank_c_records,
        "ground_truth": ground_truth_labels,
    }

