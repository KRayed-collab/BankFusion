"""
Bank A (MetroBank) Synthetic Data Generator
===========================================
Generates payment attempts for MetroBank (conventional retail banking).

1. What the file does:
   Generates synthetic rows for the bank_a_transactions table adhering to the
   traditional single-row-per-attempt model.
2. Why it exists:
   To simulate a legacy/traditional core banking system where every payment attempt
   (successful, failed, or pending) is recorded as a single transaction row.
3. What inputs it accepts:
   - account_pool: Available accounts across all banks
   - device_pool: Available synthetic device tokens
   - num_records: Number of transactions to generate
   - start_epoch: Starting timestamp in Unix epoch seconds
   - random_seed: Seed for reproducibility
4. What output it produces:
   List of dictionaries matching bank_a_transactions schema.
5. Which other files call it:
   Called by scenario orchestrators and database loaders.
6. Which DWM concept it demonstrates:
   Source system heterogeneity, single-attempt transactional grain, and cross-bank routing attributes.
7. How a student can explain it during a viva:
   "Bank A represents a standard relational core banking system. Each record represents one attempt
   to transfer money, capturing the sender, receiver, destination bank, amount in paise, payment mode,
   and terminal status."
"""

import sys
from pathlib import Path
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Indian Standard Time (UTC+05:30)
IST = timezone(timedelta(hours=5, minutes=30))


def generate_bank_a_transactions(
    accounts: Dict[str, List[Dict[str, Any]]],
    devices: List[str],
    num_records: int = 150,
    start_epoch: int = 1793512800,  # 2026-11-01 11:30:00 IST
    random_seed: int = 42,
) -> List[Dict[str, Any]]:
    """Generates synthetic transactions for Bank A (MetroBank)."""
    rng = random.Random(random_seed)
    transactions: List[Dict[str, Any]] = []

    bank_a_accounts = [acc["account_ref"] for acc in accounts["BANK_A"]]
    all_banks = ["BANK_A", "BANK_B", "BANK_C"]
    payment_modes = ["UPI", "IMPS", "NEFT", "RTGS", "CARD"]

    current_epoch = start_epoch

    for i in range(1, num_records + 1):
        txn_id = f"A-TXN-{i:05d}"
        
        # Advance timestamp by 10 to 180 seconds
        current_epoch += rng.randint(10, 180)
        dt = datetime.fromtimestamp(current_epoch, tz=IST)
        timestamp_str = dt.isoformat()

        sender = rng.choice(bank_a_accounts)

        # 60% internal to Bank A, 40% cross-bank to B or C
        dest_bank = rng.choices(all_banks, weights=[0.60, 0.25, 0.15])[0]
        dest_account_pool = [acc["account_ref"] for acc in accounts[dest_bank]]
        receiver = rng.choice(dest_account_pool)

        # Avoid self-transfer
        while receiver == sender:
            receiver = rng.choice(dest_account_pool)

        # Amount in paise: between ₹50 (5,000 paise) and ₹50,000 (5,000,000 paise)
        # Weighted towards typical retail amounts (₹200 to ₹3,000)
        if rng.random() < 0.75:
            amount_inr = rng.randint(50, 3000)
        elif rng.random() < 0.95:
            amount_inr = rng.randint(3001, 20000)
        else:
            amount_inr = rng.randint(20001, 75000)
        amount_paise = amount_inr * 100

        # Status: 85% SUCCESS, 12% FAILED, 3% PENDING
        status = rng.choices(["SUCCESS", "FAILED", "PENDING"], weights=[0.85, 0.12, 0.03])[0]
        mode = rng.choice(payment_modes)

        # Device token: 85% known device, 15% null/unknown
        device = rng.choice(devices) if rng.random() < 0.85 else None

        transactions.append({
            "transaction_id": txn_id,
            "transaction_timestamp": timestamp_str,
            "sender_account_ref": sender,
            "receiver_account_ref": receiver,
            "receiver_bank_code": dest_bank,
            "amount_paise": amount_paise,
            "payment_mode": mode,
            "transaction_status": status,
            "device_token": device,
        })

    return transactions


if __name__ == "__main__":
    from data_generation.generate_customers_and_accounts import generate_customer_and_account_pools
    pools = generate_customer_and_account_pools()
    txns = generate_bank_a_transactions(pools["accounts"], pools["devices"], num_records=10)
    print(f"Sample Bank A Record: {txns[0]}")

