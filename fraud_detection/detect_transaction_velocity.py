"""
BankFusion Fraud Detection Rule 1: Transaction Velocity Engine
==============================================================
Identifies unusually frequent payment attempts from a single source account
within a rolling 5-minute (300 seconds) inclusive window.

1. What the file does:
   Evaluates payment attempt frequency across FactTransaction records per account.
   Flags accounts and individual transactions exceeding the configured threshold (>= 4 attempts in 300s).
2. Why it exists:
   Detects automated payment scripts, rapid credential testing, or velocity bursts.
3. What inputs it accepts:
   - df: Denormalized FactTransaction DataFrame
   - window_seconds: Rolling window width in seconds (default: 300)
   - min_attempts: Threshold frequency (default: 4)
4. What output it produces:
   Tuple containing:
   - warnings: List of entity-level warning dictionaries for investigators
   - flagged_transaction_keys: Set of specific transaction_key integers marked as suspicious
5. Which other files call it:
   Called by fraud_detection/save_detection_results.py and test suites.
6. Which DWM concept it demonstrates:
   Rolling temporal window calculations, velocity pattern mining, and attempt vs settled grain evaluation.
7. How a student can explain it during a viva:
   "Rule 1 checks transaction velocity. We slide a 5-minute rolling window across all payment attempts
   per account. For MetroBank and QuickPay, this includes both failed and successful attempts.
   If an account initiates 4 or more attempts within any 300-second span, an alert is triggered."
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.path_resolver import get_config_path

CONFIG_PATH = get_config_path("detection_thresholds.json")


def load_velocity_thresholds() -> Tuple[int, int]:
    """Loads velocity window and attempt threshold from config."""
    try:
        cfg_file = get_config_path("detection_thresholds.json")
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            v = cfg["rule_1_velocity"]
            return v["window_seconds"], v["min_attempts"]
    except Exception:
        return 300, 4


def detect_velocity_bursts(
    df: pd.DataFrame,
    window_seconds: int = 300,
    min_attempts: int = 4,
) -> Tuple[List[Dict[str, Any]], Set[int]]:
    """
    Evaluates rolling velocity per account.
    Returns entity warnings and flagged transaction keys.
    """
    if df.empty:
        return [], set()

    warnings: List[Dict[str, Any]] = []
    flagged_keys: Set[int] = set()

    # Group by unique source account
    for acc_key, group in df.groupby("source_account_key"):
        sorted_group = group.sort_values("epoch_timestamp").reset_index(drop=True)
        n = len(sorted_group)
        if n < min_attempts:
            continue

        acc_ref = sorted_group["source_account_ref"].iloc[0]
        bank_code = sorted_group["bank_code"].iloc[0]

        # Slide rolling window [t_i, t_i + window_seconds]
        for i in range(n):
            start_epoch = sorted_group.loc[i, "epoch_timestamp"]
            end_epoch = start_epoch + window_seconds

            # Filter rows inside inclusive window
            window_slice = sorted_group[
                (sorted_group["epoch_timestamp"] >= start_epoch)
                & (sorted_group["epoch_timestamp"] <= end_epoch)
            ]

            if len(window_slice) >= min_attempts:
                # Add all transaction keys in this window to the flagged set
                window_keys = set(window_slice["transaction_key"])
                flagged_keys.update(window_keys)

                trigger_txn = window_slice.iloc[-1]
                evidence = (
                    f"Account {acc_ref} ({bank_code}) initiated {len(window_slice)} payment attempts "
                    f"within {window_slice.iloc[-1]['epoch_timestamp'] - start_epoch} seconds "
                    f"(Threshold: >={min_attempts} in {window_seconds}s). "
                    f"Included { (window_slice['transaction_status'] == 'FAILED').sum() } failed attempts."
                )

                warnings.append({
                    "rule_name": "VELOCITY_BURST",
                    "review_priority": "REVIEW_RECOMMENDED",
                    "entity_type": "ACCOUNT",
                    "entity_ref": f"{bank_code}:{acc_ref}",
                    "trigger_timestamp": trigger_txn["transaction_timestamp"],
                    "window_start": window_slice.iloc[0]["transaction_timestamp"],
                    "window_end": trigger_txn["transaction_timestamp"],
                    "threshold_value": min_attempts,
                    "observed_value": len(window_slice),
                    "evidence_summary": evidence,
                })
                # Break to next account to avoid redundant overlapping warning entries for same burst
                break

    return warnings, flagged_keys

