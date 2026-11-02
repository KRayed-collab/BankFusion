"""
BankFusion Fraud Detection Rule 4: Rapid Cross-Bank Movement Engine
===================================================================
Identifies rapid multi-hop interbank fund transfer chains where money passes through
intermediary accounts across different banks within a short window (10 minutes).

Conditions for detection:
1. At least two consecutive successful interbank transfers.
2. Linked by account identity: destination account of Hop 1 equals sending account of Hop 2.
3. Entire chain occurs within an inclusive 10-minute window (<= 600 seconds).
4. Each onward transfer retains between 80% and 100% of the received amount:
   0.80 * received_amount <= onward_amount <= received_amount.
5. Involves at least 3 distinct accounts and at least 2 distinct banks.
6. Evaluates SUCCESSFUL transactions only.
7. Classification: HIGH Priority Review.
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


def load_cross_bank_thresholds() -> Dict[str, Any]:
    """Loads Rule 4 thresholds from config."""
    try:
        cfg_file = get_config_path("detection_thresholds.json")
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("rule_4_cross_bank_movement", {
                "window_seconds": 600,
                "min_retention_ratio": 0.80,
                "max_retention_ratio": 1.00,
                "min_distinct_accounts": 3,
                "min_distinct_banks": 2,
            })
    except Exception:
        return {
            "window_seconds": 600,
            "min_retention_ratio": 0.80,
            "max_retention_ratio": 1.00,
            "min_distinct_accounts": 3,
            "min_distinct_banks": 2,
        }


def detect_rapid_cross_bank_chains(
    df: pd.DataFrame,
    window_seconds: int = 600,
    min_retention: float = 0.80,
    max_retention: float = 1.00,
    min_accounts: int = 3,
    min_banks: int = 2,
) -> Tuple[List[Dict[str, Any]], Set[int]]:
    """
    Detects rapid interbank transfer chains.
    Returns entity warnings with full hop route details and flagged transaction keys.
    """
    if df.empty:
        return [], set()

    # Filter to successful transactions only
    success_df = df[df["transaction_status"] == "SUCCESS"].sort_values("epoch_timestamp").reset_index(drop=True)
    if len(success_df) < 2:
        return [], set()

    warnings: List[Dict[str, Any]] = []
    flagged_keys: Set[int] = set()
    detected_chains_seen = set()

    n = len(success_df)

    src_acc_col = "source_account_key" if "source_account_key" in success_df.columns else "source_account_ref"
    dst_acc_col = "destination_account_key" if "destination_account_key" in success_df.columns else "destination_account_ref"

    for i in range(n):
        t1 = success_df.iloc[i]
        t1_key = int(t1["transaction_key"])
        t1_epoch = int(t1["epoch_timestamp"])
        t1_dest = t1[dst_acc_col]
        t1_amt = int(t1["amount_paise"])

        # Look for subsequent transfers where source account == t1_dest
        # within window_seconds (<= 600s) and after t1 (>= t1_epoch)
        candidates = success_df[
            (success_df[src_acc_col] == t1_dest)
            & (success_df["epoch_timestamp"] >= t1_epoch)
            & (success_df["epoch_timestamp"] <= t1_epoch + window_seconds)
            & (success_df["transaction_key"] != t1_key)
        ]

        for _, t2 in candidates.iterrows():
            t2_key = int(t2["transaction_key"])
            t2_epoch = int(t2["epoch_timestamp"])
            t2_amt = int(t2["amount_paise"])

            # Check retention ratio: 80% to 100%
            if not (min_retention * t1_amt <= t2_amt <= max_retention * t1_amt):
                continue

            # Chain accounts and banks
            chain_accounts = {
                str(t1[src_acc_col]),
                str(t1[dst_acc_col]),
                str(t2[dst_acc_col]),
            }
            chain_banks = {
                str(t1["bank_code"]),
                str(t1.get("receiver_bank_code") or t1["bank_code"]),
                str(t2.get("receiver_bank_code") or t2["bank_code"]),
            }

            if len(chain_accounts) < min_accounts or len(chain_banks) < min_banks:
                continue

            # We found a valid 2-hop chain! Check if there is a 3rd hop
            chain_txns = [t1, t2]
            t2_dest = t2[dst_acc_col]
            candidates_hop3 = success_df[
                (success_df[src_acc_col] == t2_dest)
                & (success_df["epoch_timestamp"] >= t2_epoch)
                & (success_df["epoch_timestamp"] <= t1_epoch + window_seconds)
                & (success_df["transaction_key"] != t1_key)
                & (success_df["transaction_key"] != t2_key)
            ]

            for _, t3 in candidates_hop3.iterrows():
                t3_amt = int(t3["amount_paise"])
                if min_retention * t2_amt <= t3_amt <= max_retention * t2_amt:
                    chain_txns.append(t3)
                    chain_accounts.add(str(t3[dst_acc_col]))
                    chain_banks.add(str(t3.get("receiver_bank_code") or t3["bank_code"]))
                    break # Take the first matching 3rd hop

            chain_key_tuple = tuple(int(t["transaction_key"]) for t in chain_txns)
            if chain_key_tuple in detected_chains_seen:
                continue
            detected_chains_seen.add(chain_key_tuple)

            for t in chain_txns:
                flagged_keys.add(int(t["transaction_key"]))

            # Build narrative explanation and route representation
            # e.g. "MetroBank: A-ACC-0012 -> Rs. 100,000 -> QuickPay Bank: B-ACC-0044 -> Rs. 90,000 -> TrustLine: C-ACC-0030"
            route_parts = []
            hop_details = []
            for idx, h in enumerate(chain_txns):
                s_bank = h["bank_code"]
                s_acc = h["source_account_ref"]
                d_bank = h.get("receiver_bank_code") or s_bank
                d_acc = h.get("destination_account_ref") or "UNKNOWN"
                amt_inr = int(h["amount_paise"]) / 100.0
                ts = h["transaction_timestamp"]

                if idx == 0:
                    route_parts.append(f"{s_bank} ({s_acc})")
                route_parts.append(f"₹{amt_inr:,.0f} ➔ {d_bank} ({d_acc})")

                prev_amt = int(chain_txns[idx - 1]["amount_paise"]) if idx > 0 else int(h["amount_paise"])
                retention_pct = round((int(h["amount_paise"]) / prev_amt) * 100, 1)
                time_diff = int(h["epoch_timestamp"]) - int(chain_txns[idx - 1]["epoch_timestamp"]) if idx > 0 else 0

                hop_details.append(
                    f"Hop {idx + 1}: {s_bank}:{s_acc} ➔ {d_bank}:{d_acc} | Amount: ₹{amt_inr:,.2f} | Time: {ts} "
                    + (f"(+{time_diff}s, retained {retention_pct}%)" if idx > 0 else "(Origin)")
                )

            linked_route_str = " ➔ ".join(route_parts)
            evidence = (
                f"Rapid linked cross-bank transfer chain detected across {len(chain_banks)} banks and {len(chain_accounts)} accounts "
                f"within {int(chain_txns[-1]['epoch_timestamp']) - t1_epoch} seconds (Threshold: <= {window_seconds}s). "
                f"Sequence: {' | '.join(hop_details)}. Potential rapid pass-through structuring."
            )

            primary_txn = chain_txns[0]
            warnings.append({
                "rule_name": "CROSS_BANK_MOVEMENT",
                "review_priority": "HIGH", # Rapid cross-bank movement is always HIGH priority
                "entity_type": "TRANSFER_CHAIN",
                "entity_ref": f"{primary_txn['bank_code']}:{primary_txn['source_transaction_id']} (Chain of {len(chain_txns)})",
                "trigger_timestamp": chain_txns[-1]["transaction_timestamp"],
                "window_start": primary_txn["transaction_timestamp"],
                "window_end": chain_txns[-1]["transaction_timestamp"],
                "threshold_value": window_seconds,
                "observed_value": int(chain_txns[-1]["epoch_timestamp"]) - t1_epoch,
                "evidence_summary": evidence,
                # Context for alert card
                "originating_bank": primary_txn["bank_code"],
                "destination_bank": chain_txns[-1].get("receiver_bank_code") or chain_txns[-1]["bank_code"],
                "sender_account_ref": primary_txn["source_account_ref"],
                "receiver_account_ref": chain_txns[-1].get("destination_account_ref"),
                "amount_paise": int(primary_txn["amount_paise"]),
                "payment_method": primary_txn.get("payment_method", "INTERBANK"),
                "transaction_status": "SUCCESS",
                "device_token": primary_txn.get("device_token"),
                "linked_route_summary": linked_route_str,
                "linked_transaction_ids": ",".join(str(int(t["transaction_key"])) for t in chain_txns),
            })

    return warnings, flagged_keys

