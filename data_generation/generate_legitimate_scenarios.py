"""
BankFusion Legitimate Scenario Generator
========================================
Generates realistic baseline transactions and benign edge cases
(including hard false positives like family shared devices and merchant spikes).

1. What the file does:
   Generates legitimate banking traffic across all three banks, including normal daily
   payments and edge cases that resemble suspicious activity without exceeding thresholds.
2. Why it exists:
   To ensure the evaluation dataset contains realistic True Negatives and False Positives,
   preventing trivial 100% accuracy claims during academic evaluation.
3. What inputs it accepts:
   - accounts: Account pools for Banks A, B, and C
   - devices: Standard device tokens
   - base_epoch: Starting timestamp
   - random_seed: Seed for reproducibility
4. What output it produces:
   Tuple of:
   - bank_a_txns: List of Bank A records
   - bank_b_events: List of Bank B records
   - bank_c_entries: List of Bank C records
   - scenario_metadata: List of label dicts for ground-truth generation
5. Which other files call it:
   Called by scenario orchestrators and database seeding scripts.
6. Which DWM concept it demonstrates:
   Class imbalance, negative class modeling, and false-positive boundary testing.
7. How a student can explain it during a viva:
   "Our generator doesn't just produce obviously normal transactions; it introduces realistic
   edge cases such as family members sharing a device or rapid utility bill payments.
   This allows us to evaluate false positive rates and discuss realistic model limitations."
"""

import sys
from pathlib import Path
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

IST = timezone(timedelta(hours=5, minutes=30))


def generate_legitimate_dataset(
    accounts: Dict[str, List[Dict[str, Any]]],
    devices: List[str],
    num_a_txns: int = 140,
    num_b_requests: int = 100,
    num_c_journals: int = 80,
    base_epoch: int = 1793512800,  # 2026-11-01 11:30:00 IST
    random_seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Generates standard legitimate transactions plus benign edge cases."""
    rng = random.Random(random_seed)

    bank_a_records: List[Dict[str, Any]] = []
    bank_b_records: List[Dict[str, Any]] = []
    bank_c_records: List[Dict[str, Any]] = []
    ground_truth_labels: List[Dict[str, Any]] = []

    # -------------------------------------------------------------------------
    # 1. Standard Bank A Transactions
    # -------------------------------------------------------------------------
    bank_a_accs = [acc["account_ref"] for acc in accounts["BANK_A"]]
    all_banks = ["BANK_A", "BANK_B", "BANK_C"]
    current_epoch = base_epoch

    for i in range(1, num_a_txns + 1):
        txn_id = f"A-TXN-{i:05d}"
        current_epoch += rng.randint(20, 150)
        dt = datetime.fromtimestamp(current_epoch, tz=IST)
        ts_str = dt.isoformat()

        sender = rng.choice(bank_a_accs)
        dest_bank = rng.choices(all_banks, weights=[0.60, 0.25, 0.15])[0]
        dest_pool = [acc["account_ref"] for acc in accounts[dest_bank]]
        receiver = rng.choice(dest_pool)
        while receiver == sender:
            receiver = rng.choice(dest_pool)

        amount_inr = rng.randint(100, 15000)
        amount_paise = amount_inr * 100
        mode = rng.choice(["UPI", "IMPS", "NEFT", "RTGS", "CARD"])
        status = rng.choices(["SUCCESS", "FAILED", "PENDING"], weights=[0.88, 0.10, 0.02])[0]
        device = rng.choice(devices[:20]) if rng.random() < 0.85 else None

        record = {
            "transaction_id": txn_id,
            "transaction_timestamp": ts_str,
            "sender_account_ref": sender,
            "receiver_account_ref": receiver,
            "receiver_bank_code": dest_bank,
            "amount_paise": amount_paise,
            "payment_mode": mode,
            "transaction_status": status,
            "device_token": device,
        }
        bank_a_records.append(record)

        ground_truth_labels.append({
            "scenario_type": "LEGITIMATE_NORMAL",
            "source_bank_code": "BANK_A",
            "source_transaction_id": txn_id,
            "source_record_refs": txn_id,
            "account_ref": sender,
            "device_token": device,
            "is_suspicious": 0,
            "notes": "Routine retail banking transaction",
        })

    # -------------------------------------------------------------------------
    # 2. Hard Legitimate Edge Case in Bank A: Rapid utility bill payments (2 txns in 2 min)
    # Below the 4-attempt threshold -> Should NOT trigger velocity warning
    # -------------------------------------------------------------------------
    edge_sender = bank_a_accs[0]
    edge_device = devices[21]
    edge_time = base_epoch + 3600
    for k in range(1, 3):
        txn_id = f"A-TXN-EDGE-{k:03d}"
        t_epoch = edge_time + (k * 40)
        dt_str = datetime.fromtimestamp(t_epoch, tz=IST).isoformat()
        rec = {
            "transaction_id": txn_id,
            "transaction_timestamp": dt_str,
            "sender_account_ref": edge_sender,
            "receiver_account_ref": bank_a_accs[1],
            "receiver_bank_code": "BANK_A",
            "amount_paise": 150000,
            "payment_mode": "UPI",
            "transaction_status": "SUCCESS",
            "device_token": edge_device,
        }
        bank_a_records.append(rec)
        ground_truth_labels.append({
            "scenario_type": "LEGITIMATE_EDGE",
            "source_bank_code": "BANK_A",
            "source_transaction_id": txn_id,
            "source_record_refs": txn_id,
            "account_ref": edge_sender,
            "device_token": edge_device,
            "is_suspicious": 0,
            "notes": "Benign rapid payment: 2 attempts in 2 mins (below threshold 4)",
        })

    # -------------------------------------------------------------------------
    # 3. Standard Bank B Events (including retry attempts)
    # -------------------------------------------------------------------------
    bank_b_accs = [acc["account_ref"] for acc in accounts["BANK_B"]]
    current_epoch = base_epoch
    b_event_counter = 1

    for req_idx in range(1, num_b_requests + 1):
        req_ref = f"B-REQ-{req_idx:05d}"
        current_epoch += rng.randint(25, 180)
        sender = rng.choice(bank_b_accs)
        dest_bank = rng.choices(all_banks, weights=[0.20, 0.65, 0.15])[0]
        dest_pool = [acc["account_ref"] for acc in accounts[dest_bank]]
        receiver = rng.choice(dest_pool)
        while receiver == sender:
            receiver = rng.choice(dest_pool)

        value_paise = rng.randint(50, 4000) * 100
        channel = rng.choice(["WALLET_TRANSFER", "QR_SCAN", "UPI_DIRECT"])
        device = rng.choice(devices[:20]) if rng.random() < 0.90 else None

        has_retry = (rng.random() < 0.12)
        attempts = 2 if has_retry else 1

        for att in range(attempts):
            evt_id = f"B-EVT-{b_event_counter:05d}"
            b_event_counter += 1
            att_epoch = current_epoch + (att * 25)
            dt_str = datetime.fromtimestamp(att_epoch, tz=IST).isoformat()
            res = "RC_05_FAILED" if (att < attempts - 1) else "RC_00_SUCCESS"

            rec = {
                "event_id": evt_id,
                "payment_request_ref": req_ref,
                "event_timestamp": dt_str,
                "sender_wallet_ref": sender,
                "beneficiary_account_ref": receiver,
                "beneficiary_bank_code": dest_bank,
                "value_paise": value_paise,
                "channel_code": channel,
                "result_code": res,
                "device_token": device,
            }
            bank_b_records.append(rec)
            ground_truth_labels.append({
                "scenario_type": "LEGITIMATE_NORMAL",
                "source_bank_code": "BANK_B",
                "source_transaction_id": evt_id,
                "source_record_refs": evt_id,
                "account_ref": sender,
                "device_token": device,
                "is_suspicious": 0,
                "notes": "Standard wallet payment event",
            })

    # -------------------------------------------------------------------------
    # 4. Hard Legitimate Edge Case: Family members sharing device (2 distinct accounts)
    # Threshold for Rule 2 is >= 3 distinct accounts -> Should NOT trigger shared device warning
    # -------------------------------------------------------------------------
    family_device = "SIM-DEVICE-FAMILY-01"
    family_acc_1 = bank_a_accs[2]
    family_acc_2 = bank_b_accs[2]

    # Family member 1 txn
    fam_txn_1 = "A-TXN-FAM-001"
    bank_a_records.append({
        "transaction_id": fam_txn_1,
        "transaction_timestamp": datetime.fromtimestamp(base_epoch + 1800, tz=IST).isoformat(),
        "sender_account_ref": family_acc_1,
        "receiver_account_ref": bank_a_accs[5],
        "receiver_bank_code": "BANK_A",
        "amount_paise": 250000,
        "payment_mode": "UPI",
        "transaction_status": "SUCCESS",
        "device_token": family_device,
    })
    ground_truth_labels.append({
        "scenario_type": "LEGITIMATE_EDGE",
        "source_bank_code": "BANK_A",
        "source_transaction_id": fam_txn_1,
        "source_record_refs": fam_txn_1,
        "account_ref": family_acc_1,
        "device_token": family_device,
        "is_suspicious": 0,
        "notes": "Benign shared hardware: 2 family members sharing tablet (below threshold 3)",
    })

    # Family member 2 txn
    fam_evt_2 = f"B-EVT-{b_event_counter:05d}"; b_event_counter += 1
    bank_b_records.append({
        "event_id": fam_evt_2,
        "payment_request_ref": "B-REQ-FAM-001",
        "event_timestamp": datetime.fromtimestamp(base_epoch + 3600, tz=IST).isoformat(),
        "sender_wallet_ref": family_acc_2,
        "beneficiary_account_ref": bank_b_accs[6],
        "beneficiary_bank_code": "BANK_B",
        "value_paise": 120000,
        "channel_code": "QR_SCAN",
        "result_code": "RC_00_SUCCESS",
        "device_token": family_device,
    })
    ground_truth_labels.append({
        "scenario_type": "LEGITIMATE_EDGE",
        "source_bank_code": "BANK_B",
        "source_transaction_id": fam_evt_2,
        "source_record_refs": fam_evt_2,
        "account_ref": family_acc_2,
        "device_token": family_device,
        "is_suspicious": 0,
        "notes": "Benign shared hardware: 2 family members sharing tablet",
    })

    # -------------------------------------------------------------------------
    # 5. Standard Bank C Ledger Entries (Balanced Double-Entry Pairs)
    # -------------------------------------------------------------------------
    bank_c_accs = [acc["account_ref"] for acc in accounts["BANK_C"]]
    current_epoch = base_epoch
    c_entry_counter = 1

    for j_idx in range(1, num_c_journals + 1):
        journal_id = f"C-J-{j_idx:05d}"
        current_epoch += rng.randint(30, 240)
        dt_str = datetime.fromtimestamp(current_epoch, tz=IST).isoformat()

        sender = rng.choice(bank_c_accs)
        receiver = rng.choice(bank_c_accs)
        while receiver == sender:
            receiver = rng.choice(bank_c_accs)

        amount_paise = rng.randint(500, 50000) * 100
        transfer_type = rng.choice(["BOOK_TRANSFER", "INTERNAL_LEDGER_TRANSFER"])
        device = rng.choice(devices[:20]) if rng.random() < 0.80 else None

        debit_id = f"C-E-{c_entry_counter:05d}"; c_entry_counter += 1
        credit_id = f"C-E-{c_entry_counter:05d}"; c_entry_counter += 1

        # Debit leg
        bank_c_records.append({
            "entry_id": debit_id, "journal_id": journal_id, "posting_timestamp": dt_str,
            "ledger_account_ref": sender, "counterparty_account_ref": receiver,
            "counterparty_bank_code": "BANK_C", "entry_side": "DEBIT",
            "amount_paise": amount_paise, "currency": "INR", "transfer_type": transfer_type,
            "entry_status": "POSTED", "device_token": device,
        })
        # Credit leg
        bank_c_records.append({
            "entry_id": credit_id, "journal_id": journal_id, "posting_timestamp": dt_str,
            "ledger_account_ref": receiver, "counterparty_account_ref": sender,
            "counterparty_bank_code": "BANK_C", "entry_side": "CREDIT",
            "amount_paise": amount_paise, "currency": "INR", "transfer_type": transfer_type,
            "entry_status": "POSTED", "device_token": device,
        })

        # Ground truth is at the normalized journal grain!
        ground_truth_labels.append({
            "scenario_type": "LEGITIMATE_NORMAL",
            "source_bank_code": "BANK_C",
            "source_transaction_id": journal_id,
            "source_record_refs": f"{debit_id},{credit_id}",
            "account_ref": sender,
            "device_token": device,
            "is_suspicious": 0,
            "notes": "Standard posted internal double-entry transfer",
        })

    return bank_a_records, bank_b_records, bank_c_records, ground_truth_labels


if __name__ == "__main__":
    from data_generation.generate_customers_and_accounts import generate_customer_and_account_pools
    pools = generate_customer_and_account_pools()
    a_rec, b_rec, c_rec, gt = generate_legitimate_dataset(pools["accounts"], pools["devices"])
    print(f"Generated Legitimate: {len(a_rec)} A txns, {len(b_rec)} B events, {len(c_rec)} C entries, {len(gt)} GT rows.")

