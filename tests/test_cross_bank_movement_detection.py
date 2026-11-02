"""
BankFusion Automated Test Suite: Rule 4 Rapid Cross-Bank Movement Detection
============================================================================
Validates detection of multi-hop rapid fund transfers across distinct accounts
and banks within a rolling 10-minute window with 80%-100% retention ratio.
"""

import sys
from pathlib import Path
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fraud_detection.detect_cross_bank_movement import (
    detect_rapid_cross_bank_chains,
    load_cross_bank_thresholds,
)


def test_cross_bank_chain_positive():
    """Validates that a 2-hop chain A -> B -> C within 300s retaining 90% is detected."""
    # Hop 1: Account A1 (Bank A) -> Account B1 (Bank B) for 1,00,000 INR
    # Hop 2: Account B1 (Bank B) -> Account C1 (Bank C) for 90,000 INR (90% retention, 120s later)
    rows = [
        {
            "transaction_key": 101,
            "source_transaction_id": "HOP-1",
            "source_account_ref": "METRO-ACC-101",
            "destination_account_ref": "QPAY-ACC-201",
            "bank_code": "METROBANK",
            "receiver_bank_code": "QUICKPAY",
            "amount_paise": 10000000,  # 1,00,000 INR
            "amount_inr": 100000.0,
            "epoch_timestamp": 1793500000,
            "transaction_timestamp": "2026-11-01T10:00:00+05:30",
            "payment_method": "IMPS",
            "transaction_status": "SUCCESS",
            "device_token": "DEV-01",
        },
        {
            "transaction_key": 102,
            "source_transaction_id": "HOP-2",
            "source_account_ref": "QPAY-ACC-201",
            "destination_account_ref": "TRUST-ACC-301",
            "bank_code": "QUICKPAY",
            "receiver_bank_code": "TRUSTLINE",
            "amount_paise": 9000000,  # 90,000 INR (90% retention)
            "amount_inr": 90000.0,
            "epoch_timestamp": 1793500120,  # +120 seconds
            "transaction_timestamp": "2026-11-01T10:02:00+05:30",
            "payment_method": "NEFT",
            "transaction_status": "SUCCESS",
            "device_token": "DEV-02",
        },
    ]

    df = pd.DataFrame(rows)
    warnings, flagged_keys = detect_rapid_cross_bank_chains(
        df,
        window_seconds=600,
        min_retention=0.80,
        max_retention=1.00,
        min_accounts=3,
        min_banks=2,
    )

    assert 101 in flagged_keys
    assert 102 in flagged_keys
    assert len(warnings) >= 1
    assert warnings[0]["rule_name"] == "CROSS_BANK_MOVEMENT"
    assert "90.0%" in warnings[0]["evidence_summary"]


def test_cross_bank_chain_negative_window_expired():
    """Confirms chain exceeding 600s window is NOT flagged as rapid movement."""
    rows = [
        {
            "transaction_key": 201,
            "source_transaction_id": "HOP-EX-1",
            "source_account_ref": "METRO-ACC-201",
            "destination_account_ref": "QPAY-ACC-202",
            "bank_code": "METROBANK",
            "receiver_bank_code": "QUICKPAY",
            "amount_paise": 5000000,
            "amount_inr": 50000.0,
            "epoch_timestamp": 1793500000,
            "transaction_timestamp": "2026-11-01T10:00:00+05:30",
            "payment_method": "IMPS",
            "transaction_status": "SUCCESS",
            "device_token": "DEV-01",
        },
        {
            "transaction_key": 202,
            "source_transaction_id": "HOP-EX-2",
            "source_account_ref": "QPAY-ACC-202",
            "destination_account_ref": "TRUST-ACC-302",
            "bank_code": "QUICKPAY",
            "receiver_bank_code": "TRUSTLINE",
            "amount_paise": 4800000,
            "amount_inr": 48000.0,
            "epoch_timestamp": 1793500000 + 1200,  # +1200s (20 mins, exceeds 10 mins)
            "transaction_timestamp": "2026-11-01T10:20:00+05:30",
            "payment_method": "NEFT",
            "transaction_status": "SUCCESS",
            "device_token": "DEV-02",
        },
    ]

    df = pd.DataFrame(rows)
    warnings, flagged_keys = detect_rapid_cross_bank_chains(
        df,
        window_seconds=600,
        min_retention=0.80,
        max_retention=1.00,
        min_accounts=3,
        min_banks=2,
    )

    assert len(flagged_keys) == 0
    assert len(warnings) == 0

