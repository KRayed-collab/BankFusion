"""
BankFusion Automated Test Suite: Rule 3 Unusually Large Amount Detection
========================================================================
Validates historical baseline calculation, multiplier thresholding, floor paise,
and fallback logic for new/sparse accounts.
"""

import sys
from pathlib import Path
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fraud_detection.detect_large_amount import (
    detect_unusually_large_amounts,
    load_large_amount_thresholds,
)


def test_large_amount_historical_baseline():
    """Confirms account with >= 5 historical txns triggers at >= 3x median & >= 50,000 INR."""
    # Build synthetic transaction history for an account
    # 5 prior txns of 10,000 INR (1,000,000 paise). Median = 10,000 INR.
    # Baseline floor = 50,000 INR. Multiplier = 3.0x -> 30,000 INR < 50,000 INR -> threshold = 50,000 INR.
    # An attempt of 60,000 INR (6,000,000 paise) should trigger.
    rows = []
    base_epoch = 1793500000
    for i in range(5):
        rows.append({
            "transaction_key": i + 1,
            "source_transaction_id": f"TXN-PREV-{i}",
            "source_account_ref": "ACC-TEST-001",
            "destination_account_ref": "ACC-REC-001",
            "bank_code": "METROBANK",
            "amount_paise": 1000000,  # 10,000 INR
            "amount_inr": 10000.0,
            "epoch_timestamp": base_epoch + (i * 3600),
            "transaction_timestamp": f"2026-11-01T{10+i}:00:00+05:30",
            "payment_method": "UPI",
            "transaction_status": "SUCCESS",
            "device_token": "DEV-01",
        })

    # The 6th transaction: 60,000 INR (exceeds floor and 3x median)
    rows.append({
        "transaction_key": 6,
        "source_transaction_id": "TXN-LARGE-FLAG",
        "source_account_ref": "ACC-TEST-001",
        "destination_account_ref": "ACC-REC-002",
        "bank_code": "METROBANK",
        "amount_paise": 6000000,  # 60,000 INR
        "amount_inr": 60000.0,
        "epoch_timestamp": base_epoch + (6 * 3600),
        "transaction_timestamp": "2026-11-01T16:00:00+05:30",
        "payment_method": "IMPS",
        "transaction_status": "SUCCESS",
        "device_token": "DEV-01",
    })

    df = pd.DataFrame(rows)
    warnings, flagged_keys = detect_unusually_large_amounts(
        df,
        historical_days=30,
        min_historical_count=5,
        multiplier=3.0,
        baseline_floor_paise=5000000,
        fallback_threshold_paise=10000000,
    )

    assert 6 in flagged_keys
    assert len(warnings) == 1
    assert warnings[0]["rule_name"] == "LARGE_AMOUNT"
    assert "ACC-TEST-001" in warnings[0]["evidence_summary"]
    assert warnings[0]["observed_value"] == 60000


def test_large_amount_fallback_new_account():
    """Confirms account with < 5 historical txns uses fallback threshold (1,00,000 INR = 10,000,000 paise)."""
    rows = [
        # Only 1 prior transaction
        {
            "transaction_key": 10,
            "source_transaction_id": "TXN-NEW-01",
            "source_account_ref": "ACC-NEW-001",
            "destination_account_ref": "ACC-REC-001",
            "bank_code": "QUICKPAY",
            "amount_paise": 2000000,  # 20,000 INR
            "amount_inr": 20000.0,
            "epoch_timestamp": 1793500000,
            "transaction_timestamp": "2026-11-01T10:00:00+05:30",
            "payment_method": "UPI",
            "transaction_status": "SUCCESS",
            "device_token": "DEV-02",
        },
        # Txn of 1,20,000 INR (12,000,000 paise) -> exceeds 1,00,000 INR fallback
        {
            "transaction_key": 11,
            "source_transaction_id": "TXN-NEW-FALLBACK-FLAG",
            "source_account_ref": "ACC-NEW-001",
            "destination_account_ref": "ACC-REC-002",
            "bank_code": "QUICKPAY",
            "amount_paise": 12000000,  # 1,20,000 INR
            "amount_inr": 120000.0,
            "epoch_timestamp": 1793501000,
            "transaction_timestamp": "2026-11-01T10:16:40+05:30",
            "payment_method": "NEFT",
            "transaction_status": "SUCCESS",
            "device_token": "DEV-02",
        },
    ]

    df = pd.DataFrame(rows)
    warnings, flagged_keys = detect_unusually_large_amounts(
        df,
        historical_days=30,
        min_historical_count=5,
        multiplier=3.0,
        baseline_floor_paise=5000000,
        fallback_threshold_paise=10000000,
    )

    assert 11 in flagged_keys
    assert 10 not in flagged_keys
    assert len(warnings) == 1
    assert "fallback large-transaction threshold" in warnings[0]["evidence_summary"]
