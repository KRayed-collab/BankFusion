"""
BankFusion Master Data Generation & Ground-Truth Orchestrator
=============================================================
Orchestrates end-to-end generation of synthetic source data across all banks
and loads both source records and separate evaluation ground-truth labels.

1. What the file does:
   Coordinates customer/account pool generation, legitimate transactions, suspicious scenarios,
   and malformed edge cases. Populates bank_a_transactions, bank_b_events, bank_c_ledger_entries,
   and evaluation_ground_truth.
2. Why it exists:
   To provide a single, reproducible entrypoint that seeds the entire fictional banking ecosystem
   into SQLite before the ETL pipeline is invoked.
3. What inputs it accepts:
   - random_seed: Seed for reproducible execution (default: 42)
   - reset_tables: Whether to clear existing records before loading (default: True)
4. What output it produces:
   Dictionary summarizing total records generated and inserted per bank and in ground truth.
5. Which other files call it:
   Called by CLI, tests, and Streamlit Page 1 & Page 2 data generation controls.
6. Which DWM concept it demonstrates:
   Heterogeneous source system provisioning, synthetic ground truth isolation, and reproducibility.
7. How a student can explain it during a viva:
   "This orchestrator executes our synthetic data generators using a fixed seed (42).
   It populates the three separate source tables with different structures, and separately stores
   ground-truth scenario labels in evaluation_ground_truth without leaking them to the warehouse."
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database_connection import SessionLocal
from database.initialize_database import initialize_database
from database.database_models import (
    BankATransaction,
    BankBEvent,
    BankCLedgerEntry,
    EvaluationGroundTruth,
)
from data_generation.generate_customers_and_accounts import generate_customer_and_account_pools
from data_generation.generate_legitimate_scenarios import generate_legitimate_dataset
from data_generation.generate_suspicious_scenarios import generate_suspicious_dataset
from data_generation.generate_bank_c_ledger import generate_bank_c_ledger_entries


def generate_and_load_full_source_data(
    random_seed: int = 42,
    reset_tables: bool = True,
) -> Dict[str, Any]:
    """
    Master function: generates all synthetic source banking traffic
    and persists records to SQLite source and evaluation tables.
    """
    if reset_tables:
        initialize_database(reset=True)

    session = SessionLocal()
    try:
        # 1. Generate core pools
        pools = generate_customer_and_account_pools(
            num_customers=60,
            num_devices=35,
            random_seed=random_seed,
        )
        accounts = pools["accounts"]
        devices = pools["devices"]

        # 2. Generate legitimate baseline + benign edge cases
        legit_a, legit_b, legit_c, legit_gt = generate_legitimate_dataset(
            accounts=accounts,
            devices=devices,
            num_a_txns=140,
            num_b_requests=100,
            num_c_journals=80,
            random_seed=random_seed,
        )

        # 3. Generate controlled suspicious scenarios
        susp_a, susp_b, susp_c, susp_gt = generate_suspicious_dataset(
            accounts=accounts,
            devices=devices,
        )

        # 4. Generate additional Bank C test journals with controlled malformed edge cases
        # (Unbalanced amounts, orphan leg, unposted) for ETL quarantine testing
        quarantine_c_entries = generate_bank_c_ledger_entries(
            accounts=accounts,
            devices=devices,
            num_journals=15,
            start_epoch=1793540000,
            include_malformed=True,
            journal_prefix="C-J-QUAR-",
            entry_prefix="C-E-QUAR-",
            start_journal_idx=1,
            start_entry_idx=1,
            random_seed=random_seed + 1,
        )

        # Combine all source records
        all_bank_a = legit_a + susp_a
        all_bank_b = legit_b + susp_b
        all_bank_c = legit_c + susp_c + quarantine_c_entries
        all_ground_truth = legit_gt + susp_gt

        # Deduplicate ground truth if any collisions
        gt_dict = {}
        for gt in all_ground_truth:
            key = (gt["source_bank_code"], gt["source_transaction_id"])
            gt_dict[key] = gt

        # Persist Bank A records
        a_objects = [BankATransaction(**rec) for rec in all_bank_a]
        session.bulk_save_objects(a_objects)

        # Persist Bank B records
        b_objects = [BankBEvent(**rec) for rec in all_bank_b]
        session.bulk_save_objects(b_objects)

        # Persist Bank C records
        c_objects = [BankCLedgerEntry(**rec) for rec in all_bank_c]
        session.bulk_save_objects(c_objects)

        # Persist Evaluation Ground Truth records
        gt_objects = [EvaluationGroundTruth(**rec) for rec in gt_dict.values()]
        session.bulk_save_objects(gt_objects)

        session.commit()

        summary = {
            "bank_a_records_generated": len(all_bank_a),
            "bank_b_events_generated": len(all_bank_b),
            "bank_c_entries_generated": len(all_bank_c),
            "ground_truth_records_stored": len(gt_dict),
            "random_seed": random_seed,
            "status": "SUCCESS",
        }
        return summary

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate and load full BankFusion source data")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for generation")
    parser.add_argument("--no-reset", action="store_true", help="Do not drop tables before loading")
    args = parser.parse_args()

    result = generate_and_load_full_source_data(
        random_seed=args.seed,
        reset_tables=not args.no_reset,
    )
    print("=== Data Generation Completed Successfully ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
