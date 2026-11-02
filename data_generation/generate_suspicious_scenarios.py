"""
BankFusion Suspicious Scenario Generator
========================================
Generates controlled, explainable suspicious transaction patterns for evaluation.

1. What the file does:
   Injects reproducible anomalies into Bank A, Bank B, and Bank C traffic:
   - Scenario A: High velocity bursts (>= 4 attempts in 5 minutes).
   - Scenario B: Shared device abuse (>= 3 distinct accounts on 1 device in 24 hours).
   - Scenario C: Dual-rule trigger (High priority review).
   - Scenario D: Cross-bank structuring transfer chain.
2. Why it exists:
   To provide predictable target patterns for evaluating the deterministic fraud-screening rules
   and computing precision, recall, and F1 metrics against isolated ground truth.
3. What inputs it accepts:
   - accounts: Account pools
   - devices: Device tokens
   - anchor_epoch: Base timestamp for synchronizing scenarios
   - random_seed: Seed for reproducibility
4. What output it produces:
   Tuple of:
   - bank_a_txns: List of suspicious Bank A records
   - bank_b_events: List of suspicious Bank B records
   - bank_c_entries: List of suspicious Bank C records
   - ground_truth_labels: Ground-truth records with is_suspicious = 1
5. Which other files call it:
   Called by full dataset builders and demo runners.
6. Which DWM concept it demonstrates:
   Anomaly detection data generation, positive class labeling, and temporal window constraint testing.
7. How a student can explain it during a viva:
   "We deliberately synthesize controlled fraud patterns matching our screening definitions:
   a burst of 4 attempts within 3 minutes by one account, and a single device used by 3 separate
   accounts across banks. This allows us to mathematically verify detector correctness."
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

IST = timezone(timedelta(hours=5, minutes=30))


def generate_suspicious_dataset(
    accounts: Dict[str, List[Dict[str, Any]]],
    devices: List[str],
    anchor_epoch: int = 1793520000,  # 2026-11-01 13:30:00 IST
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Generates controlled suspicious transactions across all banks."""

    bank_a_records: List[Dict[str, Any]] = []
    bank_b_records: List[Dict[str, Any]] = []
    bank_c_records: List[Dict[str, Any]] = []
    ground_truth_labels: List[Dict[str, Any]] = []

    # =========================================================================
    # SCENARIO 1: Velocity Burst in Bank A (Rule 1 Trigger)
    # Account A-ACC-0040 initiates 5 rapid payment attempts within 3 minutes (180s)
    # (Threshold is >= 4 attempts in 300s)
    # =========================================================================
    velocity_acc = accounts["BANK_A"][39]["account_ref"]  # A-ACC-0040
    vel_device = devices[5]
    vel_dest_acc = accounts["BANK_B"][10]["account_ref"]

    for i in range(1, 6):
        txn_id = f"A-TXN-SUSP-VEL-{i:03d}"
        t_epoch = anchor_epoch + (i * 35)  # 35s apart -> Total 175s (< 300s)
        dt_str = datetime.fromtimestamp(t_epoch, tz=IST).isoformat()
        
        # Attempts: some failed, some succeeded (attempt frequency is what triggers velocity)
        status = "FAILED" if i in [2, 3] else "SUCCESS"

        bank_a_records.append({
            "transaction_id": txn_id,
            "transaction_timestamp": dt_str,
            "sender_account_ref": velocity_acc,
            "receiver_account_ref": vel_dest_acc,
            "receiver_bank_code": "BANK_B",
            "amount_paise": 250000,  # ₹2,500
            "payment_mode": "UPI",
            "transaction_status": status,
            "device_token": vel_device,
        })

        ground_truth_labels.append({
            "scenario_type": "VELOCITY_BURST",
            "source_bank_code": "BANK_A",
            "source_transaction_id": txn_id,
            "source_record_refs": txn_id,
            "account_ref": velocity_acc,
            "device_token": vel_device,
            "is_suspicious": 1,
            "notes": "Suspicious velocity burst: 5 attempts within 175s by one account",
        })

    # =========================================================================
    # SCENARIO 2: Shared-Device Farm Across Banks (Rule 2 Trigger)
    # Device SIM-DEVICE-FARM-01 used by 4 distinct accounts within 4 hours (< 24h)
    # Accounts: 2 from Bank A, 1 from Bank B, 1 from Bank C
    # (Threshold is >= 3 distinct accounts in 24h)
    # =========================================================================
    farm_device = "SIM-DEVICE-FARM-01"
    farm_acc_a1 = accounts["BANK_A"][15]["account_ref"]
    farm_acc_a2 = accounts["BANK_A"][16]["account_ref"]
    farm_acc_b1 = accounts["BANK_B"][15]["account_ref"]
    farm_acc_c1 = accounts["BANK_C"][15]["account_ref"]

    farm_start_epoch = anchor_epoch + 14400  # 4 hours later

    # Account 1 (Bank A)
    txn_f1 = "A-TXN-FARM-001"
    bank_a_records.append({
        "transaction_id": txn_f1,
        "transaction_timestamp": datetime.fromtimestamp(farm_start_epoch + 600, tz=IST).isoformat(),
        "sender_account_ref": farm_acc_a1,
        "receiver_account_ref": accounts["BANK_A"][20]["account_ref"],
        "receiver_bank_code": "BANK_A",
        "amount_paise": 480000,
        "payment_mode": "IMPS",
        "transaction_status": "SUCCESS",
        "device_token": farm_device,
    })
    ground_truth_labels.append({
        "scenario_type": "SHARED_DEVICE_FARM",
        "source_bank_code": "BANK_A",
        "source_transaction_id": txn_f1,
        "source_record_refs": txn_f1,
        "account_ref": farm_acc_a1,
        "device_token": farm_device,
        "is_suspicious": 1,
        "notes": "Shared device farm: Account 1 on SIM-DEVICE-FARM-01",
    })

    # Account 2 (Bank A)
    txn_f2 = "A-TXN-FARM-002"
    bank_a_records.append({
        "transaction_id": txn_f2,
        "transaction_timestamp": datetime.fromtimestamp(farm_start_epoch + 1800, tz=IST).isoformat(),
        "sender_account_ref": farm_acc_a2,
        "receiver_account_ref": accounts["BANK_B"][25]["account_ref"],
        "receiver_bank_code": "BANK_B",
        "amount_paise": 490000,
        "payment_mode": "NEFT",
        "transaction_status": "SUCCESS",
        "device_token": farm_device,
    })
    ground_truth_labels.append({
        "scenario_type": "SHARED_DEVICE_FARM",
        "source_bank_code": "BANK_A",
        "source_transaction_id": txn_f2,
        "source_record_refs": txn_f2,
        "account_ref": farm_acc_a2,
        "device_token": farm_device,
        "is_suspicious": 1,
        "notes": "Shared device farm: Account 2 on SIM-DEVICE-FARM-01",
    })

    # Account 3 (Bank B)
    evt_f3 = "B-EVT-FARM-001"
    bank_b_records.append({
        "event_id": evt_f3,
        "payment_request_ref": "B-REQ-FARM-001",
        "event_timestamp": datetime.fromtimestamp(farm_start_epoch + 3600, tz=IST).isoformat(),
        "sender_wallet_ref": farm_acc_b1,
        "beneficiary_account_ref": accounts["BANK_B"][30]["account_ref"],
        "beneficiary_bank_code": "BANK_B",
        "value_paise": 450000,
        "channel_code": "WALLET_TRANSFER",
        "result_code": "RC_00_SUCCESS",
        "device_token": farm_device,
    })
    ground_truth_labels.append({
        "scenario_type": "SHARED_DEVICE_FARM",
        "source_bank_code": "BANK_B",
        "source_transaction_id": evt_f3,
        "source_record_refs": evt_f3,
        "account_ref": farm_acc_b1,
        "device_token": farm_device,
        "is_suspicious": 1,
        "notes": "Shared device farm: Account 3 on SIM-DEVICE-FARM-01 (triggers threshold >=3)",
    })

    # Account 4 (Bank C Internal Book Transfer)
    j_f4 = "C-J-FARM-001"
    e_f4_deb = "C-E-FARM-001"
    e_f4_crd = "C-E-FARM-002"
    f4_time = datetime.fromtimestamp(farm_start_epoch + 5400, tz=IST).isoformat()
    dest_c_acc = accounts["BANK_C"][28]["account_ref"]

    bank_c_records.append({
        "entry_id": e_f4_deb, "journal_id": j_f4, "posting_timestamp": f4_time,
        "ledger_account_ref": farm_acc_c1, "counterparty_account_ref": dest_c_acc,
        "counterparty_bank_code": "BANK_C", "entry_side": "DEBIT",
        "amount_paise": 475000, "currency": "INR", "transfer_type": "BOOK_TRANSFER",
        "entry_status": "POSTED", "device_token": farm_device,
    })
    bank_c_records.append({
        "entry_id": e_f4_crd, "journal_id": j_f4, "posting_timestamp": f4_time,
        "ledger_account_ref": dest_c_acc, "counterparty_account_ref": farm_acc_c1,
        "counterparty_bank_code": "BANK_C", "entry_side": "CREDIT",
        "amount_paise": 475000, "currency": "INR", "transfer_type": "BOOK_TRANSFER",
        "entry_status": "POSTED", "device_token": farm_device,
    })
    ground_truth_labels.append({
        "scenario_type": "SHARED_DEVICE_FARM",
        "source_bank_code": "BANK_C",
        "source_transaction_id": j_f4,
        "source_record_refs": f"{e_f4_deb},{e_f4_crd}",
        "account_ref": farm_acc_c1,
        "device_token": farm_device,
        "is_suspicious": 1,
        "notes": "Shared device farm: Account 4 on SIM-DEVICE-FARM-01",
    })

    # =========================================================================
    # SCENARIO 3: Cross-Bank Multi-Hop Structuring Chain (Demonstration)
    # Bank A (A-ACC-0012) -> Bank B (B-ACC-0044) -> Bank C (C-ACC-0030)
    # =========================================================================
    hop_time = anchor_epoch + 25000
    hop_a_acc = accounts["BANK_A"][11]["account_ref"]  # A-ACC-0012
    hop_b_acc = accounts["BANK_B"][43]["account_ref"]  # B-ACC-0044
    hop_c_acc = accounts["BANK_C"][29]["account_ref"]  # C-ACC-0030

    # Hop 1: Bank A to Bank B (₹8,500 = 850,000 paise)
    hop_txn_1 = "A-TXN-HOP-001"
    bank_a_records.append({
        "transaction_id": hop_txn_1,
        "transaction_timestamp": datetime.fromtimestamp(hop_time, tz=IST).isoformat(),
        "sender_account_ref": hop_a_acc,
        "receiver_account_ref": hop_b_acc,
        "receiver_bank_code": "BANK_B",
        "amount_paise": 850000,
        "payment_mode": "IMPS",
        "transaction_status": "SUCCESS",
        "device_token": devices[10],
    })
    ground_truth_labels.append({
        "scenario_type": "CROSS_BANK_CHAIN",
        "source_bank_code": "BANK_A",
        "source_transaction_id": hop_txn_1,
        "source_record_refs": hop_txn_1,
        "account_ref": hop_a_acc,
        "device_token": devices[10],
        "is_suspicious": 1,
        "notes": "Multi-hop structuring Hop 1: Bank A -> Bank B (₹8,500)",
    })

    # Hop 2: Bank B to Bank C (₹8,200 = 820,000 paise, 15 mins later)
    hop_evt_2 = "B-EVT-HOP-001"
    bank_b_records.append({
        "event_id": hop_evt_2,
        "payment_request_ref": "B-REQ-HOP-001",
        "event_timestamp": datetime.fromtimestamp(hop_time + 900, tz=IST).isoformat(),
        "sender_wallet_ref": hop_b_acc,
        "beneficiary_account_ref": hop_c_acc,
        "beneficiary_bank_code": "BANK_C",
        "value_paise": 820000,
        "channel_code": "UPI_DIRECT",
        "result_code": "RC_00_SUCCESS",
        "device_token": devices[11],
    })
    ground_truth_labels.append({
        "scenario_type": "CROSS_BANK_CHAIN",
        "source_bank_code": "BANK_B",
        "source_transaction_id": hop_evt_2,
        "source_record_refs": hop_evt_2,
        "account_ref": hop_b_acc,
        "device_token": devices[11],
        "is_suspicious": 1,
        "notes": "Multi-hop structuring Hop 2: Bank B -> Bank C (₹8,200)",
    })

    return bank_a_records, bank_b_records, bank_c_records, ground_truth_labels


if __name__ == "__main__":
    from data_generation.generate_customers_and_accounts import generate_customer_and_account_pools
    pools = generate_customer_and_account_pools()
    a_s, b_s, c_s, gt_s = generate_suspicious_dataset(pools["accounts"], pools["devices"])
    print(f"Generated Suspicious: {len(a_s)} A txns, {len(b_s)} B events, {len(c_s)} C entries, {len(gt_s)} GT rows.")

