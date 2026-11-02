"""
BankFusion Bank Comparison Analytics
====================================
Computes cross-bank comparative performance metrics:
Volume, failure rates, average ticket size, and cross-bank flow distributions.
"""

import sys
from pathlib import Path
from typing import Dict, Any
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def generate_bank_comparison_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes a comprehensive comparative summary table for Banks A, B, and C.
    """
    if df.empty:
        return pd.DataFrame()

    summary_rows = []
    banks = df["bank_code"].unique()

    for b in sorted(banks):
        b_df = df[df["bank_code"] == b]
        total_attempts = len(b_df)
        success_df = b_df[b_df["transaction_status"] == "SUCCESS"]
        failed_df = b_df[b_df["transaction_status"] == "FAILED"]

        success_count = len(success_df)
        failed_count = len(failed_df)
        success_rate = (success_count / total_attempts * 100.0) if total_attempts > 0 else 0.0
        failure_rate = (failed_count / total_attempts * 100.0) if total_attempts > 0 else 0.0

        total_volume_inr = b_df["amount_inr"].sum()
        settled_volume_inr = success_df["amount_inr"].sum()
        avg_amount_inr = b_df["amount_inr"].mean() if total_attempts > 0 else 0.0

        summary_rows.append({
            "Bank Code": b,
            "Bank Name": b_df["bank_name"].iloc[0] if "bank_name" in b_df else b,
            "Bank Model": b_df["bank_type"].iloc[0] if "bank_type" in b_df else "",
            "Total Attempts": total_attempts,
            "Successful Count": success_count,
            "Failed Count": failed_count,
            "Success Rate (%)": round(success_rate, 2),
            "Failure Rate (%)": round(failure_rate, 2),
            "Total Volume (₹)": round(total_volume_inr, 2),
            "Settled Volume (₹)": round(settled_volume_inr, 2),
            "Avg Transaction (₹)": round(avg_amount_inr, 2),
        })

    return pd.DataFrame(summary_rows)

