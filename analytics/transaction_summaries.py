"""
BankFusion Transaction Summaries Analytics
==========================================
Computes categorical distributions across payment methods and terminal statuses.
"""

import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def get_payment_method_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Computes distribution by payment method."""
    if df.empty:
        return pd.DataFrame()

    dist = (
        df.groupby("payment_method", as_index=False)
        .agg(
            transaction_count=("transaction_key", "count"),
            total_volume_inr=("amount_inr", "sum"),
            avg_amount_inr=("amount_inr", "mean"),
        )
        .sort_values("transaction_count", ascending=False)
    )
    total_txns = dist["transaction_count"].sum()
    dist["share_pct"] = round((dist["transaction_count"] / total_txns * 100.0), 2)
    return dist


def get_status_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Computes distribution by transaction terminal status."""
    if df.empty:
        return pd.DataFrame()

    dist = (
        df.groupby("transaction_status", as_index=False)
        .agg(
            count=("transaction_key", "count"),
            volume_inr=("amount_inr", "sum"),
        )
        .sort_values("count", ascending=False)
    )
    total = dist["count"].sum()
    dist["percentage"] = round((dist["count"] / total * 100.0), 2)
    return dist

