"""
BankFusion Transaction Trends Analytics
=======================================
Computes temporal time-series aggregations across hours, days, and time-of-day categories.
"""

import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def get_hourly_activity_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregates transaction volume and frequency by hour of the day (0 to 23)."""
    if df.empty:
        return pd.DataFrame()

    hourly = (
        df.groupby("hour", as_index=False)
        .agg(
            transaction_count=("transaction_key", "count"),
            total_volume_inr=("amount_inr", "sum"),
            avg_volume_inr=("amount_inr", "mean"),
        )
        .sort_values("hour")
    )
    return hourly


def get_daily_trend_series(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregates transaction metrics by full_date."""
    if df.empty:
        return pd.DataFrame()

    daily = (
        df.groupby("full_date", as_index=False)
        .agg(
            total_attempts=("transaction_key", "count"),
            successful_volume_inr=(
                "amount_inr",
                lambda s: s[df.loc[s.index, "transaction_status"] == "SUCCESS"].sum(),
            ),
            total_volume_inr=("amount_inr", "sum"),
        )
        .sort_values("full_date")
    )
    return daily

