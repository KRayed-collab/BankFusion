"""
BankFusion Customer and Account Pool Generator
==============================================
Generates synthetic customer identities, bank-specific account references,
and standardized device tokens with reproducible randomness.

1. What the file does:
   Creates realistic customer profiles (names, IDs), maps them to accounts across
   Bank A, Bank B, and Bank C, and creates a pool of synthetic device tokens.
2. Why it exists:
   To establish a consistent, reproducible pool of participants for all bank transactions,
   cross-bank transfers, and shared-device scenarios without hardcoded or external data.
3. What inputs it accepts:
   - num_customers: Total unique customers to generate (default: 60)
   - num_devices: Total unique device tokens (default: 35)
   - random_seed: Seed for deterministic execution (default: 42)
4. What output it produces:
   Dictionary containing:
   - 'customers': List of customer metadata dicts
   - 'accounts': Dict keyed by bank_code ('BANK_A', 'BANK_B', 'BANK_C') with account dicts
   - 'devices': List of device token strings
5. Which other files call it:
   Called by bank-specific generators and scenario generators.
6. Which DWM concept it demonstrates:
   Conformed dimension preparation, entity identity resolution, and surrogate key source feeds.
7. How a student can explain it during a viva:
   "This module programmatically generates consistent synthetic banking customers and accounts
   across all three banks using a fixed random seed. It guarantees that accounts have distinct
   identifiers per bank while allowing controlled simulation of cross-bank transfers and shared hardware."
"""

import sys
from pathlib import Path
import random
from typing import Dict, List, Any

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


FIRST_NAMES = [
    "Aarav", "Aditi", "Amit", "Ananya", "Arjun", "Deepak", "Divya", "Gaurav",
    "Ishaan", "Kavya", "Manish", "Meera", "Neha", "Nikhil", "Pooja", "Pranav",
    "Priya", "Rahul", "Rhea", "Rohan", "Sanjay", "Shreya", "Siddharth", "Sneha",
    "Tanvi", "Varun", "Vikram", "Vivek", "Zoya", "Karan"
]

LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Mehta", "Iyer", "Nair", "Reddy", "Rao",
    "Singh", "Kumar", "Gupta", "Joshi", "Bose", "Das", "Chopra", "Malhotra",
    "Deshmukh", "Kulkarni", "Pillai", "Menon", "Sen", "Bhat", "Chawla", "Kapoor"
]


def generate_customer_and_account_pools(
    num_customers: int = 60,
    num_devices: int = 35,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """Generates reproducible customer, account, and device token pools."""
    rng = random.Random(random_seed)

    customers: List[Dict[str, Any]] = []
    accounts: Dict[str, List[Dict[str, Any]]] = {
        "BANK_A": [],
        "BANK_B": [],
        "BANK_C": [],
    }

    # Generate customer profiles
    for i in range(1, num_customers + 1):
        cust_id = f"CUST-{i:04d}"
        first_name = rng.choice(FIRST_NAMES)
        last_name = rng.choice(LAST_NAMES)
        full_name = f"{first_name} {last_name}"

        customers.append({
            "customer_id": cust_id,
            "full_name": full_name,
            "city": rng.choice(["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Pune", "Chennai", "Kolkata"]),
        })

    # Generate accounts for Bank A (MetroBank - Conventional Retail)
    # Most customers get a Savings account, some get Current
    for i, cust in enumerate(customers):
        acc_ref = f"A-ACC-{i + 1:04d}"
        acc_type = "CURRENT" if (i % 7 == 0) else "SAVINGS"
        accounts["BANK_A"].append({
            "account_ref": acc_ref,
            "customer_id": cust["customer_id"],
            "account_type": acc_type,
            "created_at": "2026-01-15T09:00:00+05:30",
        })

    # Generate accounts for Bank B (QuickPay Bank - Digital Wallets)
    for i, cust in enumerate(customers):
        acc_ref = f"B-ACC-{i + 1:04d}"
        accounts["BANK_B"].append({
            "account_ref": acc_ref,
            "customer_id": cust["customer_id"],
            "account_type": "WALLET",
            "created_at": "2026-02-01T10:00:00+05:30",
        })

    # Generate accounts for Bank C (TrustLine Bank - Ledger Accounts)
    for i, cust in enumerate(customers):
        acc_ref = f"C-ACC-{i + 1:04d}"
        acc_type = "COMMERCIAL" if (i % 5 == 0) else "PERSONAL"
        accounts["BANK_C"].append({
            "account_ref": acc_ref,
            "customer_id": cust["customer_id"],
            "account_type": acc_type,
            "created_at": "2026-01-01T08:00:00+05:30",
        })

    # Generate standardized hardware device tokens
    devices = [f"SIM-DEVICE-{i:03d}" for i in range(1, num_devices + 1)]

    return {
        "customers": customers,
        "accounts": accounts,
        "devices": devices,
    }


if __name__ == "__main__":
    pools = generate_customer_and_account_pools()
    print(f"Generated {len(pools['customers'])} customers.")
    print(f"Bank A Accounts: {len(pools['accounts']['BANK_A'])}")
    print(f"Bank B Accounts: {len(pools['accounts']['BANK_B'])}")
    print(f"Bank C Accounts: {len(pools['accounts']['BANK_C'])}")
    print(f"Synthetic Devices: {len(pools['devices'])}")

