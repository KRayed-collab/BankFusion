"""
Bank C (TrustLine Bank) Double-Entry Ledger Generator
=====================================================
Generates balanced debit and credit ledger entries for TrustLine Bank.

1. What the file does:
   Generates paired DEBIT and CREDIT rows for bank_c_ledger_entries.
   Enforces Pacioli double-entry bookkeeping principles for internal transfers.
2. Why it exists:
   To simulate an accounting ledger core banking system where transactions do not exist
   as single rows, but as balanced entries tied by a journal_id.
3. What inputs it accepts:
   - accounts: Available accounts across all banks
   - devices: Available synthetic device tokens
   - num_journals: Number of business transfers to simulate
   - start_epoch: Starting timestamp in Unix epoch seconds
   - include_malformed: Flag to inject controlled malformed journals for ETL quarantine testing
   - random_seed: Seed for reproducibility
4. What output it produces:
   List of dictionaries matching bank_c_ledger_entries schema (approx 2x num_journals).
5. Which other files call it:
   Called by scenario orchestrators and database loaders.
6. Which DWM concept it demonstrates:
   Grain transformation (2:1 source-to-fact ratio), debit-credit balancing, and ETL quarantine handling.
7. How a student can explain it during a viva:
   "TrustLine Bank uses double-entry bookkeeping. Every business transfer produces two distinct rows:
   one debiting the sender and one crediting the receiver under the same journal_id.
   During ETL, our pipeline validates that both legs match before producing exactly one warehouse transaction."
"""

import sys
from pathlib import Path
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

IST = timezone(timedelta(hours=5, minutes=30))


def generate_bank_c_ledger_entries(
    accounts: Dict[str, List[Dict[str, Any]]],
    devices: List[str],
    num_journals: int = 100,
    start_epoch: int = 1793512800,
    include_malformed: bool = True,
    journal_prefix: str = "C-J-",
    entry_prefix: str = "C-E-",
    start_journal_idx: int = 1,
    start_entry_idx: int = 1,
    random_seed: int = 42,
) -> List[Dict[str, Any]]:
    """Generates synthetic double-entry ledger entries for Bank C."""
    rng = random.Random(random_seed)
    entries: List[Dict[str, Any]] = []

    bank_c_accounts = [acc["account_ref"] for acc in accounts["BANK_C"]]
    transfer_types = ["BOOK_TRANSFER", "INTERNAL_LEDGER_TRANSFER"]

    current_epoch = start_epoch
    entry_counter = start_entry_idx

    for j_idx in range(start_journal_idx, start_journal_idx + num_journals):
        journal_id = f"{journal_prefix}{j_idx:05d}"
        current_epoch += rng.randint(20, 240)
        dt = datetime.fromtimestamp(current_epoch, tz=IST)
        timestamp_str = dt.isoformat()

        sender = rng.choice(bank_c_accounts)
        receiver = rng.choice(bank_c_accounts)
        while receiver == sender:
            receiver = rng.choice(bank_c_accounts)

        # Amount in paise: ₹500 to ₹100,000 (50,000 to 10,000,000 paise)
        amount_inr = rng.randint(500, 100000)
        amount_paise = amount_inr * 100
        transfer_type = rng.choice(transfer_types)
        device = rng.choice(devices) if rng.random() < 0.80 else None

        # Determine if this journal should be a deliberate edge case (approx 5% if enabled)
        is_malformed = include_malformed and (j_idx % 25 == 0)

        if not is_malformed:
            # 1. Normal Balanced Journal (1 Debit, 1 Credit, Posted)
            debit_entry_id = f"{entry_prefix}{entry_counter:05d}"
            entry_counter += 1
            credit_entry_id = f"{entry_prefix}{entry_counter:05d}"
            entry_counter += 1

            # DEBIT leg (Sender)
            entries.append({
                "entry_id": debit_entry_id,
                "journal_id": journal_id,
                "posting_timestamp": timestamp_str,
                "ledger_account_ref": sender,
                "counterparty_account_ref": receiver,
                "counterparty_bank_code": "BANK_C",
                "entry_side": "DEBIT",
                "amount_paise": amount_paise,
                "currency": "INR",
                "transfer_type": transfer_type,
                "entry_status": "POSTED",
                "device_token": device,
            })

            # CREDIT leg (Receiver) - Reciprocal
            entries.append({
                "entry_id": credit_entry_id,
                "journal_id": journal_id,
                "posting_timestamp": timestamp_str,
                "ledger_account_ref": receiver,
                "counterparty_account_ref": sender,
                "counterparty_bank_code": "BANK_C",
                "entry_side": "CREDIT",
                "amount_paise": amount_paise,
                "currency": "INR",
                "transfer_type": transfer_type,
                "entry_status": "POSTED",
                "device_token": device,
            })
        else:
            # Inject controlled malformed test case
            malform_type = (j_idx // 25) % 3
            if malform_type == 1:
                # Type 1: Unbalanced amounts
                debit_id = f"{entry_prefix}{entry_counter:05d}"; entry_counter += 1
                credit_id = f"{entry_prefix}{entry_counter:05d}"; entry_counter += 1
                entries.append({
                    "entry_id": debit_id, "journal_id": journal_id, "posting_timestamp": timestamp_str,
                    "ledger_account_ref": sender, "counterparty_account_ref": receiver,
                    "counterparty_bank_code": "BANK_C", "entry_side": "DEBIT",
                    "amount_paise": amount_paise, "currency": "INR", "transfer_type": transfer_type,
                    "entry_status": "POSTED", "device_token": device,
                })
                entries.append({
                    "entry_id": credit_id, "journal_id": journal_id, "posting_timestamp": timestamp_str,
                    "ledger_account_ref": receiver, "counterparty_account_ref": sender,
                    "counterparty_bank_code": "BANK_C", "entry_side": "CREDIT",
                    "amount_paise": amount_paise - 5000,  # Corrupted mismatched amount!
                    "currency": "INR", "transfer_type": transfer_type,
                    "entry_status": "POSTED", "device_token": device,
                })
            elif malform_type == 2:
                # Type 2: Orphan journal (Missing credit leg)
                debit_id = f"{entry_prefix}{entry_counter:05d}"; entry_counter += 1
                entries.append({
                    "entry_id": debit_id, "journal_id": journal_id, "posting_timestamp": timestamp_str,
                    "ledger_account_ref": sender, "counterparty_account_ref": receiver,
                    "counterparty_bank_code": "BANK_C", "entry_side": "DEBIT",
                    "amount_paise": amount_paise, "currency": "INR", "transfer_type": transfer_type,
                    "entry_status": "POSTED", "device_token": device,
                })
            else:
                # Type 3: Unposted status
                debit_id = f"{entry_prefix}{entry_counter:05d}"; entry_counter += 1
                credit_id = f"{entry_prefix}{entry_counter:05d}"; entry_counter += 1
                entries.append({
                    "entry_id": debit_id, "journal_id": journal_id, "posting_timestamp": timestamp_str,
                    "ledger_account_ref": sender, "counterparty_account_ref": receiver,
                    "counterparty_bank_code": "BANK_C", "entry_side": "DEBIT",
                    "amount_paise": amount_paise, "currency": "INR", "transfer_type": transfer_type,
                    "entry_status": "UNPOSTED", "device_token": device,
                })
                entries.append({
                    "entry_id": credit_id, "journal_id": journal_id, "posting_timestamp": timestamp_str,
                    "ledger_account_ref": receiver, "counterparty_account_ref": sender,
                    "counterparty_bank_code": "BANK_C", "entry_side": "CREDIT",
                    "amount_paise": amount_paise, "currency": "INR", "transfer_type": transfer_type,
                    "entry_status": "UNPOSTED", "device_token": device,
                })

    return entries


if __name__ == "__main__":
    from data_generation.generate_customers_and_accounts import generate_customer_and_account_pools
    pools = generate_customer_and_account_pools()
    entries = generate_bank_c_ledger_entries(pools["accounts"], pools["devices"], num_journals=10)
    print(f"Generated {len(entries)} ledger entries for 10 journals.")
    print(f"Sample Entry: {entries[0]}")
