"""
BankFusion Fraud Detection Rule 2: Shared-Device Usage Engine
=============================================================
Identifies synthetic device tokens associated with an unusually large number
of distinct source accounts within a rolling 24-hour (86,400 seconds) inclusive window.

1. What the file does:
   Filters out unknown devices and evaluates the count of unique sending accounts using
   the same device token. Triggers when distinct sending accounts >= 3 in a 24-hour span.
2. Why it exists:
   Detects emulator farms, stolen credential rings, or fraudulent hardware multiplexing.
3. What inputs it accepts:
   - df: Denormalized FactTransaction DataFrame
   - window_seconds: Rolling window in seconds (default: 86400)
   - min_distinct_accounts: Threshold distinct accounts (default: 3)
4. What output it produces:
   Tuple containing:
   - warnings: List of entity-level warning dictionaries
   - flagged_transaction_keys: Set of specific transaction_key integers marked as suspicious
5. Which other files call it:
   Called by fraud_detection/save_detection_results.py and test suites.
6. Which DWM concept it demonstrates:
   Graph/association linkage screening, exclusion of null surrogate members, and temporal association mining.
7. How a student can explain it during a viva:
   "Rule 2 identifies hardware multiplexing. We slide a 24-hour window over transactions per device,
   excluding the unknown device surrogate. If 3 or more distinct accounts transact from the same device
   within 24 hours, an alert is raised. A shared device does not guarantee crime—it could be a shopkeeper."
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


def load_shared_device_thresholds() -> Tuple[int, int]:
    """Loads shared-device window and distinct account threshold from config."""
    try:
        cfg_file = get_config_path("detection_thresholds.json")
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            d = cfg["rule_2_shared_device"]
            return d["window_seconds"], d["min_distinct_accounts"]
    except Exception:
        return 86400, 3


def detect_shared_device_abuse(
    df: pd.DataFrame,
    window_seconds: int = 86400,
    min_distinct_accounts: int = 3,
) -> Tuple[List[Dict[str, Any]], Set[int]]:
    """
    Evaluates rolling shared-device usage across distinct sending accounts.
    Explicitly ignores surrogate UNKNOWN_DEVICE records.
    Returns entity warnings and flagged transaction keys.
    """
    if df.empty:
        return [], set()

    # Exclude unknown devices
    valid_devices = df[
        (df["is_device_known"] == 1) & (df["device_token"] != "UNKNOWN_DEVICE")
    ]
    if valid_devices.empty:
        return [], set()

    warnings: List[Dict[str, Any]] = []
    flagged_keys: Set[int] = set()

    # Group by physical device token
    for dev_token, group in valid_devices.groupby("device_token"):
        sorted_group = group.sort_values("epoch_timestamp").reset_index(drop=True)
        unique_accs_overall = sorted_group["source_account_key"].nunique()
        if unique_accs_overall < min_distinct_accounts:
            continue

        n = len(sorted_group)
        warned = False
        # Slide rolling window [t_i - window_seconds, t_i]
        for i in range(n):
            current_epoch = sorted_group.loc[i, "epoch_timestamp"]
            window_start_epoch = current_epoch - window_seconds

            window_slice = sorted_group[
                (sorted_group["epoch_timestamp"] >= window_start_epoch)
                & (sorted_group["epoch_timestamp"] <= current_epoch)
            ]

            distinct_accs = window_slice["source_account_key"].nunique()
            if distinct_accs >= min_distinct_accounts:
                # Flag all transactions on this device in the window
                window_keys = set(window_slice["transaction_key"])
                flagged_keys.update(window_keys)

                if not warned:
                    trigger_txn = window_slice.iloc[-1]
                    acc_list = sorted_group["source_account_ref"].unique().tolist()
                    evidence = (
                        f"Device {dev_token} utilized by {distinct_accs} distinct sending accounts "
                        f"({', '.join(acc_list[:4])}) within rolling 24 hours "
                        f"(Threshold: >={min_distinct_accounts} distinct accounts in {window_seconds // 3600}h)."
                    )

                    warnings.append({
                        "rule_name": "SHARED_DEVICE",
                        "review_priority": "REVIEW_RECOMMENDED",
                        "entity_type": "DEVICE",
                        "entity_ref": str(dev_token),
                        "trigger_timestamp": trigger_txn["transaction_timestamp"],
                        "window_start": window_slice.iloc[0]["transaction_timestamp"],
                        "window_end": trigger_txn["transaction_timestamp"],
                        "threshold_value": min_distinct_accounts,
                        "observed_value": distinct_accs,
                        "evidence_summary": evidence,
                    })
                    warned = True

    return warnings, flagged_keys

