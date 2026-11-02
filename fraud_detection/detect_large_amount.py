"""
BankFusion Fraud Detection Rule 3: Unusually Large Transaction Amount Engine
=============================================================================
Identifies transactions with amounts significantly exceeding an account's
historical baseline (>= 3x median and >= Rs. 50,000) or exceeding a fallback threshold
(>= Rs. 1,00,000) when insufficient historical baseline exists (< 5 transactions).

1. What the file does:
   Evaluates each transaction against strictly preceding transactions for the same sending
   account over a rolling 30-day window to prevent future-data leakage.
2. Why it exists:
   Detects sudden account takeovers, drain attempts, or abnormal corporate high-value fraud.
3. What inputs it accepts:
   - df: Denormalized FactTransaction DataFrame
   - historical_days: Days to look back (default: 30)
   - min_historical_count: Min transactions required for baseline (default: 5)
   - multiplier: Historical median multiplier (default: 3.0)
   - baseline_floor_paise: Min amount floor when baseline exists (default: 5,000,000 paise / Rs. 50,000)
   - fallback_threshold_paise: Threshold when history < 5 (default: 10,000,000 paise / Rs. 1,00,000)
4. What output it produces:
   Tuple containing:
   - warnings: List of alert dictionaries with detailed explanation
   - flagged_transaction_keys: Set of transaction_key integers marked as suspicious
5. Which other files call it:
   Called by fraud_detection/save_detection_results.py and test suites.
6. Which DWM concept it demonstrates:
   Historical profiling, dynamic threshold baseline calculation, and leakage-free temporal slicing.
7. How a student can explain it during a viva:
   "Rule 3 evaluates transaction size relative to an account's normal spending. If an account has at least
   5 transactions in the prior 30 days, we compute its historical median and flag any payment that is at least
   3x the median and at least Rs. 50,000. For new accounts with fewer than 5 payments, a fallback threshold of
   Rs. 1,00,000 applies."
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.path_resolver import get_config_path

CONFIG_PATH = get_config_path("detection_thresholds.json")


def load_large_amount_thresholds() -> Dict[str, Any]:
    """Loads Rule 3 thresholds from config."""
    try:
        cfg_file = get_config_path("detection_thresholds.json")
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("rule_3_large_amount", {
                "historical_period_days": 30,
                "min_historical_txns": 5,
                "historical_multiplier": 3.0,
                "baseline_floor_paise": 5000000,
                "fallback_threshold_paise": 10000000,
            })
    except Exception:
        return {
            "historical_period_days": 30,
            "min_historical_txns": 5,
            "historical_multiplier": 3.0,
            "baseline_floor_paise": 5000000,
            "fallback_threshold_paise": 10000000,
        }


def detect_unusually_large_amounts(
    df: pd.DataFrame,
    historical_days: int = 30,
    min_historical_count: int = 5,
    multiplier: float = 3.0,
    baseline_floor_paise: int = 5000000,      # Rs. 50,000
    fallback_threshold_paise: int = 10000000, # Rs. 1,00,000
) -> Tuple[List[Dict[str, Any]], Set[int]]:
    """
    Evaluates each transaction against strictly historical baseline transactions.
    Returns entity warnings and flagged transaction keys.
    """
    if df.empty:
        return [], set()

    warnings: List[Dict[str, Any]] = []
    flagged_keys: Set[int] = set()

    history_window_sec = historical_days * 86400

    acc_col = "source_account_key" if "source_account_key" in df.columns else "source_account_ref"

    # Group by sending account to evaluate history
    for acc_key, group in df.groupby(acc_col):
        sorted_txns = group.sort_values("epoch_timestamp").reset_index(drop=True)
        n = len(sorted_txns)

        acc_ref = sorted_txns["source_account_ref"].iloc[0]
        bank_code = sorted_txns["bank_code"].iloc[0]

        for i in range(n):
            current_txn = sorted_txns.iloc[i]
            current_epoch = int(current_txn["epoch_timestamp"])
            current_amt_paise = int(current_txn["amount_paise"])
            current_amt_inr = current_amt_paise / 100.0

            # Find historical transactions strictly preceding current_epoch within 30-day window
            # strictly before: epoch_timestamp < current_epoch to avoid data leakage
            window_start_epoch = current_epoch - history_window_sec
            history_slice = sorted_txns[
                (sorted_txns["epoch_timestamp"] >= window_start_epoch)
                & (sorted_txns["epoch_timestamp"] < current_epoch)
            ]

            hist_count = len(history_slice)
            is_flagged = False
            evidence = ""
            observed_val = current_amt_paise
            threshold_val = 0

            if hist_count >= min_historical_count:
                # Historical baseline approach
                median_paise = int(history_slice["amount_paise"].median())
                calculated_threshold = int(median_paise * multiplier)
                effective_threshold = max(calculated_threshold, baseline_floor_paise)
                threshold_val = effective_threshold

                if current_amt_paise >= effective_threshold:
                    is_flagged = True
                    evidence = (
                        f"Amount Rs. {current_amt_inr:,.2f} is unusually large for account {acc_ref} ({bank_code}). "
                        f"Preceding 30-day median: Rs. {median_paise / 100:,.2f} over {hist_count} transactions. "
                        f"Threshold: >= {multiplier}x median (Rs. {calculated_threshold / 100:,.2f}) with floor Rs. {baseline_floor_paise / 100:,.2f}."
                    )
            else:
                # Insufficient history -> Fallback threshold
                threshold_val = fallback_threshold_paise
                if current_amt_paise >= fallback_threshold_paise:
                    is_flagged = True
                    evidence = (
                        f"Amount Rs. {current_amt_inr:,.2f} triggered fallback large-transaction threshold "
                        f"for account {acc_ref} ({bank_code}) with insufficient history ({hist_count} previous txns, required {min_historical_count}). "
                        f"Threshold used: Rs. {fallback_threshold_paise / 100:,.2f}."
                    )

            if is_flagged:
                t_key = int(current_txn["transaction_key"])
                flagged_keys.add(t_key)

                dest_bank = current_txn.get("receiver_bank_code") or bank_code
                dest_acc = current_txn.get("destination_account_ref") or "UNKNOWN"

                warnings.append({
                    "rule_name": "LARGE_AMOUNT",
                    "review_priority": "REVIEW", # Elevated by orchestrator if multiple rules
                    "entity_type": "TRANSACTION",
                    "entity_ref": f"{bank_code}:{current_txn['source_transaction_id']}",
                    "trigger_timestamp": current_txn["transaction_timestamp"],
                    "window_start": history_slice.iloc[0]["transaction_timestamp"] if hist_count > 0 else current_txn["transaction_timestamp"],
                    "window_end": current_txn["transaction_timestamp"],
                    "threshold_value": threshold_val // 100, # Display in INR
                    "observed_value": observed_val // 100,
                    "evidence_summary": evidence,
                    # Context for Review Queue card
                    "originating_bank": bank_code,
                    "destination_bank": dest_bank,
                    "sender_account_ref": acc_ref,
                    "receiver_account_ref": dest_acc,
                    "amount_paise": current_amt_paise,
                    "payment_method": current_txn.get("payment_method", "UNKNOWN"),
                    "transaction_status": current_txn.get("transaction_status", "UNKNOWN"),
                    "device_token": current_txn.get("device_token"),
                    "linked_transaction_ids": str(t_key),
                })

    return warnings, flagged_keys

