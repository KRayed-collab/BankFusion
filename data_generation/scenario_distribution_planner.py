"""
BankFusion Synthetic Scenario Distribution Planner
===================================================
Orchestrates balanced, explainable multi-bank synthetic transaction generation
matching configurable target distributions (Default: 80% CLEAR, 15% REVIEW, 5% AUTO_BLOCKED).

Key Architectural Principles:
1. Strict Separation: The generator plans scenario attributes (amounts, intervals, device reuse)
   that naturally trigger or clear the deterministic fraud rules.
2. No Cheating / No Direct Assignment: Does NOT set is_predicted_suspicious, factor counts,
   or enforcement statuses. All classifications are derived independently by the detection
   engine and enforcement policy.
3. Multi-Bank Representation: Distributes transactions across Bank A, Bank B, and Bank C.
4. Clean Isolation: Clean transactions use dedicated accounts and isolated devices with
   typical amounts (< Rs. 15,000) so they genuinely receive 0 triggered factors.
5. Accurate Accounting: Accounts for all supporting/setup transactions in the distribution.
"""

import sys
import json
import time
import random
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.path_resolver import get_config_path
from database.database_models import (
    BankATransaction,
    BankBEvent,
    BankCLedgerEntry,
)

IST = timezone(timedelta(hours=5, minutes=30))
logger = logging.getLogger("BankFusion.ScenarioPlanner")


def load_simulation_distribution() -> Dict[str, Any]:
    """
    Loads configurable scenario target percentages from simulation_distribution.json
    or detection_thresholds.json, with safe fallback.
    """
    default_config = {
        "CLEAR": 80.0,
        "REVIEW_PENDING": 15.0,
        "AUTO_BLOCKED": 5.0,
        "default_random_seed": 42,
    }

    try:
        cfg_path = get_config_path("simulation_distribution.json")
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                targets = data.get("target_percentages", {})
                return {
                    "CLEAR": float(targets.get("CLEAR", 80.0)),
                    "REVIEW_PENDING": float(targets.get("REVIEW_PENDING", 15.0)),
                    "AUTO_BLOCKED": float(targets.get("AUTO_BLOCKED", 5.0)),
                    "default_random_seed": data.get("default_random_seed", 42),
                }
    except Exception as exc:
        logger.warning(f"Could not load simulation_distribution.json: {exc}")

    try:
        dt_path = get_config_path("detection_thresholds.json")
        if dt_path.exists():
            with open(dt_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                dist = data.get("simulation_distribution", {})
                if dist:
                    return {
                        "CLEAR": float(dist.get("clear_target_pct", 80.0)),
                        "REVIEW_PENDING": float(dist.get("review_pending_target_pct", 15.0)),
                        "AUTO_BLOCKED": float(dist.get("auto_blocked_target_pct", 5.0)),
                        "default_random_seed": dist.get("default_random_seed", 42),
                    }
    except Exception as exc:
        logger.warning(f"Could not load simulation_distribution from detection_thresholds.json: {exc}")

    return default_config


class ScenarioDistributionPlanner:
    """
    Plans and generates synthetic transactions matching target distributions across Banks A, B, and C.
    """

    def __init__(self, seed: Optional[int] = None):
        cfg = load_simulation_distribution()
        self.target_clear_pct = cfg["CLEAR"]
        self.target_review_pct = cfg["REVIEW_PENDING"]
        self.target_blocked_pct = cfg["AUTO_BLOCKED"]
        self.seed = seed if seed is not None else cfg.get("default_random_seed", 42)
        self.rng = random.Random(self.seed)

    def plan_batch_counts(self, total_transactions: int) -> Dict[str, int]:
        """
        Computes integer allocation of transactions to categories based on target percentages.
        """
        if total_transactions <= 0:
            return {"CLEAR": 0, "REVIEW_PENDING": 0, "AUTO_BLOCKED": 0}

        if total_transactions < 10:
            # For small ticks (e.g. 3 transactions), sample probabilistically
            p_blk = self.target_blocked_pct / 100.0
            p_rev = self.target_review_pct / 100.0

            roll = self.rng.random()
            if roll < p_blk:
                return {"CLEAR": max(0, total_transactions - 1), "REVIEW_PENDING": 0, "AUTO_BLOCKED": 1}
            elif roll < (p_blk + p_rev):
                return {"CLEAR": max(0, total_transactions - 1), "REVIEW_PENDING": 1, "AUTO_BLOCKED": 0}
            else:
                return {"CLEAR": total_transactions, "REVIEW_PENDING": 0, "AUTO_BLOCKED": 0}

        # For larger batches, compute exact rounded allocations
        n_blocked = int(round(total_transactions * (self.target_blocked_pct / 100.0)))
        n_review = int(round(total_transactions * (self.target_review_pct / 100.0)))
        n_clear = total_transactions - n_blocked - n_review

        if n_clear < 0:
            n_clear = 0
            n_review = total_transactions - n_blocked

        return {
            "CLEAR": n_clear,
            "REVIEW_PENDING": n_review,
            "AUTO_BLOCKED": n_blocked,
        }

    def generate_batch(
        self,
        batch_size: int = 100,
        anchor_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Generates source records for Banks A, B, and C satisfying the planned distribution.
        """
        if anchor_time is None:
            anchor_time = datetime.now(IST)

        anchor_epoch = int(anchor_time.timestamp())
        batch_slug = f"{int(time.time() * 1000) % 1000000}-{self.rng.randint(100, 999)}"

        counts = self.plan_batch_counts(batch_size)
        n_clear = counts["CLEAR"]
        n_review = counts["REVIEW_PENDING"]
        n_blocked = counts["AUTO_BLOCKED"]

        bank_a_records: List[BankATransaction] = []
        bank_b_records: List[BankBEvent] = []
        bank_c_records: List[BankCLedgerEntry] = []
        generated_ids: List[str] = []
        gt_metadata: List[Dict[str, Any]] = []

        seq = 0
        global_bank_idx = 0

        def get_next_bank_idx() -> int:
            nonlocal global_bank_idx
            idx = global_bank_idx % 3
            global_bank_idx += 1
            return idx

        # ---------------------------------------------------------------------
        # 1. AUTO-BLOCKED SCENARIO (>= 3 factors: Velocity + Device + Large Amount)
        # ---------------------------------------------------------------------
        # Shared device token with 2 setup accounts (Rule 2 setup).
        # Target attacker initiates n_blocked rapid attempts (at least 4 in <= 300s)
        # with amounts >= Rs. 100,000 (Rule 3 fallback).
        # Setup transactions naturally trigger Rule 2 only (1 factor) and count
        # as part of n_review!
        # ---------------------------------------------------------------------
        review_allocated_from_setup = 0

        if n_blocked > 0:
            blk_shared_dev = f"SIM-DEV-BLKFARM-{batch_slug}"
            atk_acc = f"A-ACC-ATK-{batch_slug}"
            rec_acc = f"B-ACC-REC-{batch_slug}"

            # If n_review >= 2, we generate 2 setup accounts that use the shared device
            # at t - 400s (outside 5-min velocity window, small amounts).
            # These 2 transactions naturally become REVIEW_PENDING (Rule 2 only).
            setup_accounts_needed = min(2, n_review)
            for s_idx in range(setup_accounts_needed):
                seq += 1
                t_setup = anchor_epoch - 380 - (s_idx * 30)
                t_setup_iso = datetime.fromtimestamp(t_setup, tz=IST).isoformat()
                s_id = f"A-TXN-BLKSUP{s_idx+1}-{batch_slug}"
                rec_setup = BankATransaction(
                    transaction_id=s_id,
                    transaction_timestamp=t_setup_iso,
                    sender_account_ref=f"A-ACC-BLKSUP{s_idx+1}-{batch_slug}",
                    receiver_account_ref=rec_acc,
                    receiver_bank_code="QUICKPAY",
                    amount_paise=100000,  # Rs. 1,000
                    payment_mode="UPI",
                    transaction_status="SUCCESS",
                    device_token=blk_shared_dev,
                )
                bank_a_records.append(rec_setup)
                generated_ids.append(s_id)
                gt_metadata.append({
                    "source_id": s_id,
                    "intended_tier": "REVIEW_PENDING",
                    "intended_factors": ["SHARED_DEVICE"],
                })
                review_allocated_from_setup += 1

            # Ensure minimum 4 attempts for velocity rule
            vel_attempts_count = max(4, n_blocked)
            # Spacing between attempts within 180 seconds (< 300s)
            time_offsets = [180 - int(i * (150 / max(1, vel_attempts_count))) for i in range(vel_attempts_count)]

            for i in range(vel_attempts_count):
                seq += 1
                off = time_offsets[i]
                t_iso = datetime.fromtimestamp(anchor_epoch - off, tz=IST).isoformat()
                r_id = f"A-TXN-AUTOBLK-{i+1}-{batch_slug}"
                amt_paise = 12000000 + (i * 500000)  # Rs. 1,20,000 to Rs. 1,45,000 (>= Rs. 1,00,000 fallback)

                rec = BankATransaction(
                    transaction_id=r_id,
                    transaction_timestamp=t_iso,
                    sender_account_ref=atk_acc,
                    receiver_account_ref=rec_acc,
                    receiver_bank_code="QUICKPAY",
                    amount_paise=amt_paise,
                    payment_mode="UPI",
                    transaction_status="PENDING",
                    device_token=blk_shared_dev,
                )
                bank_a_records.append(rec)
                generated_ids.append(r_id)
                gt_metadata.append({
                    "source_id": r_id,
                    "intended_tier": "AUTO_BLOCKED",
                    "intended_factors": ["VELOCITY_BURST", "SHARED_DEVICE", "LARGE_AMOUNT"],
                })

            # Update n_blocked to actual velocity attempts generated if batch_size accommodates it
            actual_blk_generated = vel_attempts_count
        else:
            actual_blk_generated = 0

        # ---------------------------------------------------------------------
        # 2. REVIEW_PENDING SCENARIOS (1 or 2 factors)
        # ---------------------------------------------------------------------
        remaining_review = max(0, n_review - review_allocated_from_setup)
        # Adjust n_clear if actual_blk_generated differed slightly from n_blocked
        total_non_clear = actual_blk_generated + review_allocated_from_setup + remaining_review
        if total_non_clear > batch_size:
            remaining_review = max(0, batch_size - actual_blk_generated - review_allocated_from_setup)

        rev_generated = 0
        rev_sub_idx = 0

        while rev_generated < remaining_review:
            rev_sub_idx += 1
            rem = remaining_review - rev_generated
            sub_slug = f"REV{rev_sub_idx}-{batch_slug}"

            # Sub-scenario A: Cross-Bank Rapid Movement (Hop 1 & Hop 2: 2 transactions, Rule 4 only)
            if rem >= 2 and (rev_sub_idx % 4 == 1):
                hop1_id = f"A-TXN-REV-XB1-{sub_slug}"
                hop2_id = f"B-EVT-REV-XB2-{sub_slug}"
                t_hop1_iso = datetime.fromtimestamp(anchor_epoch - 180, tz=IST).isoformat()
                t_hop2_iso = datetime.fromtimestamp(anchor_epoch - 60, tz=IST).isoformat()

                # Hop 1: Bank A to Bank B (Rs. 45,000)
                rec_hop1 = BankATransaction(
                    transaction_id=hop1_id,
                    transaction_timestamp=t_hop1_iso,
                    sender_account_ref=f"A-ACC-XB-SND-{sub_slug}",
                    receiver_account_ref=f"B-ACC-XB-MID-{sub_slug}",
                    receiver_bank_code="BANK_B",
                    amount_paise=4500000,  # Rs. 45,000 (< Rs. 50,000)
                    payment_mode="IMPS",
                    transaction_status="SUCCESS",
                    device_token=f"DEV-XB1-{sub_slug}",
                )
                # Hop 2: Bank B to Bank C (Rs. 40,000 = 88.8% retention)
                rec_hop2 = BankBEvent(
                    event_id=hop2_id,
                    payment_request_ref=f"B-REQ-XB2-{sub_slug}",
                    event_timestamp=t_hop2_iso,
                    sender_wallet_ref=f"B-ACC-XB-MID-{sub_slug}",
                    beneficiary_account_ref=f"C-ACC-XB-END-{sub_slug}",
                    beneficiary_bank_code="BANK_C",
                    value_paise=4000000,  # Rs. 40,000
                    channel_code="UPI_DIRECT",
                    result_code="RC_00_SUCCESS",
                    device_token=f"DEV-XB2-{sub_slug}",
                )
                bank_a_records.append(rec_hop1)
                bank_b_records.append(rec_hop2)
                generated_ids.extend([hop1_id, hop2_id])
                gt_metadata.extend([
                    {"source_id": hop1_id, "intended_tier": "REVIEW_PENDING", "intended_factors": ["CROSS_BANK_MOVEMENT"]},
                    {"source_id": hop2_id, "intended_tier": "REVIEW_PENDING", "intended_factors": ["CROSS_BANK_MOVEMENT"]},
                ])
                rev_generated += 2

            # Sub-scenario B: Velocity Burst (4 rapid attempts, Rule 1 only)
            elif rem >= 4 and (rev_sub_idx % 4 == 2):
                vel_acc = f"A-ACC-REV-VEL-{sub_slug}"
                vel_dev = f"DEV-REV-VEL-ISOLATED-{sub_slug}"
                for v_i in range(1, 5):
                    seq += 1
                    t_iso = datetime.fromtimestamp(anchor_epoch - (160 - v_i * 30), tz=IST).isoformat()
                    r_id = f"A-TXN-REV-VEL{v_i}-{sub_slug}"
                    rec = BankATransaction(
                        transaction_id=r_id,
                        transaction_timestamp=t_iso,
                        sender_account_ref=vel_acc,
                        receiver_account_ref=f"B-ACC-DEST{v_i}-{sub_slug}",
                        receiver_bank_code="QUICKPAY",
                        amount_paise=200000,  # Rs. 2,000 (< Rs. 50,000)
                        payment_mode="UPI",
                        transaction_status="PENDING",
                        device_token=vel_dev,
                    )
                    bank_a_records.append(rec)
                    generated_ids.append(r_id)
                    gt_metadata.append({
                        "source_id": r_id,
                        "intended_tier": "REVIEW_PENDING",
                        "intended_factors": ["VELOCITY_BURST"],
                    })
                rev_generated += 4

            # Sub-scenario C: Large Amount (Amount >= Rs. 1,00,000, isolated device, Rule 3 only)
            else:
                b_type = get_next_bank_idx()
                seq += 1
                amt_paise = self.rng.choice([12000000, 13500000, 15000000])  # Rs. 1.2L - 1.5L
                dev_tok = f"DEV-REV-AMT-ISOLATED-{sub_slug}"
                snd_acc = f"ACC-REV-AMT-{sub_slug}"
                rec_acc = f"ACC-DEST-AMT-{sub_slug}"
                t_iso = datetime.fromtimestamp(anchor_epoch - 20 - rev_generated, tz=IST).isoformat()

                if b_type == 0:
                    r_id = f"A-TXN-REV-AMT-{sub_slug}"
                    rec = BankATransaction(
                        transaction_id=r_id,
                        transaction_timestamp=t_iso,
                        sender_account_ref=f"A-{snd_acc}",
                        receiver_account_ref=f"B-{rec_acc}",
                        receiver_bank_code="QUICKPAY",
                        amount_paise=amt_paise,
                        payment_mode="IMPS",
                        transaction_status="PENDING",
                        device_token=dev_tok,
                    )
                    bank_a_records.append(rec)
                elif b_type == 1:
                    r_id = f"B-EVT-REV-AMT-{sub_slug}"
                    rec = BankBEvent(
                        event_id=r_id,
                        payment_request_ref=f"B-REQ-AMT-{sub_slug}",
                        event_timestamp=t_iso,
                        sender_wallet_ref=f"B-{snd_acc}",
                        beneficiary_account_ref=f"A-{rec_acc}",
                        beneficiary_bank_code="METROBANK",
                        value_paise=amt_paise,
                        channel_code="UPI_DIRECT",
                        result_code="RC_99_PENDING",
                        device_token=dev_tok,
                    )
                    bank_b_records.append(rec)
                else:
                    r_id = f"C-JRN-REV-AMT-{sub_slug}"
                    entry_deb = BankCLedgerEntry(
                        entry_id=f"C-ENT-AMT1-{sub_slug}",
                        journal_id=r_id,
                        posting_timestamp=t_iso,
                        ledger_account_ref=f"C-{snd_acc}",
                        counterparty_account_ref=f"C-{rec_acc}",
                        counterparty_bank_code="BANK_C",
                        entry_side="DEBIT",
                        amount_paise=amt_paise,
                        currency="INR",
                        transfer_type="BOOK_TRANSFER",
                        entry_status="POSTED",
                        device_token=dev_tok,
                    )
                    entry_crd = BankCLedgerEntry(
                        entry_id=f"C-ENT-AMT2-{sub_slug}",
                        journal_id=r_id,
                        posting_timestamp=t_iso,
                        ledger_account_ref=f"C-{rec_acc}",
                        counterparty_account_ref=f"C-{snd_acc}",
                        counterparty_bank_code="BANK_C",
                        entry_side="CREDIT",
                        amount_paise=amt_paise,
                        currency="INR",
                        transfer_type="BOOK_TRANSFER",
                        entry_status="POSTED",
                        device_token=dev_tok,
                    )
                    bank_c_records.extend([entry_deb, entry_crd])

                generated_ids.append(r_id)
                gt_metadata.append({
                    "source_id": r_id,
                    "intended_tier": "REVIEW_PENDING",
                    "intended_factors": ["LARGE_AMOUNT"],
                })
                rev_generated += 1

        # ---------------------------------------------------------------------
        # 3. CLEAN TRANSACTIONS (0 factors)
        # ---------------------------------------------------------------------
        # Fill remaining slots up to batch_size with guaranteed clean transactions
        # ---------------------------------------------------------------------
        current_total = len(generated_ids)
        needed_clean = max(0, batch_size - current_total)

        clean_amounts = [
            25000, 50000, 80000, 120000, 180000, 250000, 400000, 650000, 950000, 1200000
        ]  # Rs. 250 to Rs. 12,000

        for c_idx in range(needed_clean):
            seq += 1
            cln_slug = f"CLN{c_idx+1}-{batch_slug}"
            b_type = get_next_bank_idx()

            amt_paise = self.rng.choice(clean_amounts)
            dev_tok = f"DEV-CLN-{cln_slug}"
            snd_acc = f"ACC-CLN-{cln_slug}"
            rec_acc = f"ACC-DEST-{cln_slug}"
            t_iso = datetime.fromtimestamp(anchor_epoch - 5 - c_idx, tz=IST).isoformat()

            if b_type == 0:
                r_id = f"A-TXN-CLN-{cln_slug}"
                rec = BankATransaction(
                    transaction_id=r_id,
                    transaction_timestamp=t_iso,
                    sender_account_ref=f"A-{snd_acc}",
                    receiver_account_ref=f"B-{rec_acc}",
                    receiver_bank_code="QUICKPAY",
                    amount_paise=amt_paise,
                    payment_mode=self.rng.choice(["UPI", "IMPS", "NEFT"]),
                    transaction_status="PENDING",
                    device_token=dev_tok,
                )
                bank_a_records.append(rec)
            elif b_type == 1:
                r_id = f"B-EVT-CLN-{cln_slug}"
                rec = BankBEvent(
                    event_id=r_id,
                    payment_request_ref=f"B-REQ-CLN-{cln_slug}",
                    event_timestamp=t_iso,
                    sender_wallet_ref=f"B-{snd_acc}",
                    beneficiary_account_ref=f"A-{rec_acc}",
                    beneficiary_bank_code="METROBANK",
                    value_paise=amt_paise,
                    channel_code=self.rng.choice(["WALLET_TRANSFER", "UPI_DIRECT", "QR_SCAN"]),
                    result_code="RC_99_PENDING",
                    device_token=dev_tok,
                )
                bank_b_records.append(rec)
            else:
                r_id = f"C-JRN-CLN-{cln_slug}"
                entry_deb = BankCLedgerEntry(
                    entry_id=f"C-ENT-CLN1-{cln_slug}",
                    journal_id=r_id,
                    posting_timestamp=t_iso,
                    ledger_account_ref=f"C-{snd_acc}",
                    counterparty_account_ref=f"C-{rec_acc}",
                    counterparty_bank_code="BANK_C",
                    entry_side="DEBIT",
                    amount_paise=amt_paise,
                    currency="INR",
                    transfer_type="BOOK_TRANSFER",
                    entry_status="POSTED",
                    device_token=dev_tok,
                )
                entry_crd = BankCLedgerEntry(
                    entry_id=f"C-ENT-CLN2-{cln_slug}",
                    journal_id=r_id,
                    posting_timestamp=t_iso,
                    ledger_account_ref=f"C-{rec_acc}",
                    counterparty_account_ref=f"C-{snd_acc}",
                    counterparty_bank_code="BANK_C",
                    entry_side="CREDIT",
                    amount_paise=amt_paise,
                    currency="INR",
                    transfer_type="BOOK_TRANSFER",
                    entry_status="POSTED",
                    device_token=dev_tok,
                )
                bank_c_records.extend([entry_deb, entry_crd])

            generated_ids.append(r_id)
            gt_metadata.append({
                "source_id": r_id,
                "intended_tier": "CLEAR",
                "intended_factors": [],
            })

        planned_summary = {
            "CLEAR": needed_clean,
            "REVIEW_PENDING": review_allocated_from_setup + rev_generated,
            "AUTO_BLOCKED": actual_blk_generated,
        }

        return {
            "bank_a_records": bank_a_records,
            "bank_b_records": bank_b_records,
            "bank_c_records": bank_c_records,
            "generated_ids": generated_ids,
            "ground_truth_metadata": gt_metadata,
            "planned_counts": planned_summary,
            "total_fact_transactions": len(generated_ids),
            "batch_slug": batch_slug,
        }
