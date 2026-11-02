"""
BankFusion OLAP Multidimensional Analytical Engine
==================================================
Implements core Data Warehousing OLAP cube operations:
Slice, Dice, Drill-down, and Roll-up over FactTransaction and dimension joins.

1. What the file does:
   Executes multidimensional queries:
   - Slice: Pinning one dimension to a single value (e.g., Bank = 'BANK_A')
   - Dice: Sub-cube extraction via multi-dimensional filtering
   - Roll-up: Aggregating from fine grains (hourly/daily) to coarse grains (monthly/quarterly)
   - Drill-down: Navigating from summary levels down to granular temporal intervals
2. Why it exists:
   Fulfills the central DWM requirement for multidimensional analysis beyond 2D SQL filters.
3. What inputs it accepts:
   - df: Denormalized FactTransaction DataFrame
   - filter criteria and aggregation level parameters
4. What output it produces:
   Aggregated and filtered Pandas DataFrames with transaction counts and rupee volumes.
5. Which other files call it:
   Called by Streamlit Page 2 (Data Warehouse) and test suites.
6. Which DWM concept it demonstrates:
   OLAP operations, multidimensional data cubes, and hierarchical aggregation.
7. How a student can explain it during a viva:
   "OLAP allows multidimensional exploration. A 'Slice' selects one bank across all dimensions;
   a 'Dice' isolates a sub-cube by filtering across multiple dimensions simultaneously (e.g.,
   MetroBank UPI payments in November); 'Roll-up' sums hourly data to daily totals; and 'Drill-down'
   decomposes a quarterly total into daily activity."
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def olap_slice(df: pd.DataFrame, dimension_col: str, value: Any) -> pd.DataFrame:
    """
    OLAP Slice: Fastens a single dimension to one specific coordinate value.
    Example: dimension_col='bank_code', value='BANK_A'
    """
    if df.empty or dimension_col not in df.columns:
        return pd.DataFrame()
    return df[df[dimension_col] == value].copy()


def olap_dice(
    df: pd.DataFrame,
    banks: Optional[List[str]] = None,
    methods: Optional[List[str]] = None,
    statuses: Optional[List[str]] = None,
    time_of_day: Optional[List[str]] = None,
    min_amount_inr: Optional[float] = None,
    max_amount_inr: Optional[float] = None,
) -> pd.DataFrame:
    """
    OLAP Dice: Extracts a sub-cube by applying simultaneous filtering criteria
    across multiple dimensions.
    """
    if df.empty:
        return pd.DataFrame()

    sub_cube = df.copy()

    if banks:
        sub_cube = sub_cube[sub_cube["bank_code"].isin(banks)]
    if methods:
        sub_cube = sub_cube[sub_cube["payment_method"].isin(methods)]
    if statuses:
        sub_cube = sub_cube[sub_cube["transaction_status"].isin(statuses)]
    if time_of_day:
        sub_cube = sub_cube[sub_cube["time_of_day"].isin(time_of_day)]
    if min_amount_inr is not None:
        sub_cube = sub_cube[sub_cube["amount_inr"] >= min_amount_inr]
    if max_amount_inr is not None:
        sub_cube = sub_cube[sub_cube["amount_inr"] <= max_amount_inr]

    return sub_cube


def olap_roll_up(df: pd.DataFrame, level: str = "daily") -> pd.DataFrame:
    """
    OLAP Roll-up: Climbs up the aggregation hierarchy to produce higher-level summaries.
    Levels:
    - 'hourly': Group by date and hour
    - 'daily': Group by full_date
    - 'monthly': Group by year and month_name
    - 'quarterly': Group by year and quarter
    """
    if df.empty:
        return pd.DataFrame()

    if level == "hourly":
        group_cols = ["full_date", "hour"]
    elif level == "daily":
        group_cols = ["full_date"]
    elif level == "monthly":
        group_cols = ["year", "month_name"]
    elif level == "quarterly":
        group_cols = ["year", "quarter"]
    else:
        group_cols = ["full_date"]

    agg_df = (
        df.groupby(group_cols, as_index=False)
        .agg(
            total_attempts=("transaction_key", "count"),
            successful_count=(
                "transaction_status",
                lambda s: (s == "SUCCESS").sum(),
            ),
            failed_count=(
                "transaction_status",
                lambda s: (s == "FAILED").sum(),
            ),
            total_amount_paise=("amount_paise", "sum"),
            total_amount_inr=("amount_inr", "sum"),
            avg_amount_inr=("amount_inr", "mean"),
        )
    )
    return agg_df


def olap_drill_down(
    df: pd.DataFrame,
    parent_level: str,
    parent_value: Any,
    child_level: str,
) -> pd.DataFrame:
    """
    OLAP Drill-down: Navigates from a parent aggregate node down into more detailed child grains.
    Example: parent_level='quarter', parent_value=4 -> child_level='monthly' or 'daily'
    """
    if df.empty or parent_level not in df.columns:
        return pd.DataFrame()

    filtered = df[df[parent_level] == parent_value]
    return olap_roll_up(filtered, level=child_level)

