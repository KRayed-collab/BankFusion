"""
Bank B (QuickPay Bank) Synthetic Data Generator
===============================================
Generates payment events for QuickPay Bank (event-driven digital wallet).

1. What the file does:
   Generates synthetic rows for the bank_b_events table adhering to the event-stream model
   where retry attempts share a common payment_request_ref.
2. Why it exists:
   To simulate modern digital payment platforms where a single user payment intent
   can produce multiple lifecycle events (e.g., initial failure, retry, success).
3. What inputs it accepts:
   - accounts: Available accounts across all banks
   - devices: Available synthetic device tokens
   - num_requests: Number of payment intents to simulate
   - start_epoch: Starting timestamp in Unix epoch seconds
   - random_seed: Seed for reproducibility
4. What output it produces:
   List of dictionaries matching bank_b_events schema.
5. Which other files call it:
   Called by scenario orchestrators and database loaders.
6. Which DWM concept it demonstrates:
   Event grain versus transactional grain, retry lineage, and source-to-target mapping of result codes.
7. How a student can explain it during a viva:
   "Bank B models an event log rather than a traditional ledger. A single payment intent
   (payment_request_ref) can trigger multiple events (event_id) due to retries. For instance,
   a network failure event followed by a successful retry event are two distinct source rows."
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


def generate_bank_b_events(
    accounts: Dict[str, List[Dict[str, Any]]],
    devices: List[str],
    num_requests: int = 120,
    start_epoch: int = 1793512800,
    random_seed: int = 42,
) -> List[Dict[str, Any]]:
    """Generates synthetic events for Bank B (QuickPay Bank) with retry patterns."""
    rng = random.Random(random_seed)
    events: List[Dict[str, Any]] = []

    bank_b_accounts = [acc["account_ref"] for acc in accounts["BANK_B"]]
    all_banks = ["BANK_A", "BANK_B", "BANK_C"]
    channels = ["WALLET_TRANSFER", "QR_SCAN", "UPI_DIRECT"]

    current_epoch = start_epoch
    event_counter = 1

    for req_idx in range(1, num_requests + 1):
        req_ref = f"B-REQ-{req_idx:05d}"
        current_epoch += rng.randint(15, 200)

        sender = rng.choice(bank_b_accounts)
        dest_bank = rng.choices(all_banks, weights=[0.20, 0.65, 0.15])[0]
        dest_account_pool = [acc["account_ref"] for acc in accounts[dest_bank]]
        receiver = rng.choice(dest_account_pool)

        while receiver == sender:
            receiver = rng.choice(dest_account_pool)

        # Value in paise: typical wallet amounts ₹20 to ₹5,000 (2,000 to 500,000 paise)
        amount_inr = rng.randint(20, 5000)
        value_paise = amount_inr * 100

        channel = rng.choice(channels)
        device = rng.choice(devices) if rng.random() < 0.90 else None

        # Simulate retry behavior: 15% of payment requests experience 1-2 retry events
        has_retry = (rng.random() < 0.15)
        num_attempts = rng.randint(2, 3) if has_retry else 1

        for attempt in range(num_attempts):
            evt_id = f"B-EVT-{event_counter:05d}"
            event_counter += 1

            attempt_epoch = current_epoch + (attempt * rng.randint(10, 45))
            dt = datetime.fromtimestamp(attempt_epoch, tz=IST)
            timestamp_str = dt.isoformat()

            # If multi-attempt, earlier attempts failed, final attempt may succeed
            if attempt < num_attempts - 1:
                result_code = "RC_05_FAILED"
            else:
                result_code = rng.choices(["RC_00_SUCCESS", "RC_05_FAILED", "RC_99_PENDING"], weights=[0.88, 0.10, 0.02])[0]

            events.append({
                "event_id": evt_id,
                "payment_request_ref": req_ref,
                "event_timestamp": timestamp_str,
                "sender_wallet_ref": sender,
                "beneficiary_account_ref": receiver,
                "beneficiary_bank_code": dest_bank,
                "value_paise": value_paise,
                "channel_code": channel,
                "result_code": result_code,
                "device_token": device,
            })

    return events


if __name__ == "__main__":
    from data_generation.generate_customers_and_accounts import generate_customer_and_account_pools
    pools = generate_customer_and_account_pools()
    events = generate_bank_b_events(pools["accounts"], pools["devices"], num_requests=10)
    print(f"Generated {len(events)} events from 10 payment requests.")
    print(f"Sample Event: {events[0]}")

