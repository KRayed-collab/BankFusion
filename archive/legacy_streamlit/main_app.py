"""
BankFusion: Multi-Bank Data Warehouse & Fraud Analytics Platform
================================================================
Operational Fraud-Monitoring Station
Entrypoint for Streamlit Navigation (Two-Page Operational Architecture)
- Page 1: Fraud Review Queue
- Page 2: Transaction Feed
"""

import sys
from pathlib import Path
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Two-Page Native Streamlit Navigation
queue_page = st.Page(
    "pages/1_Fraud_Review_Queue.py",
    title="Fraud Review Queue",
    icon="🛡️",
    default=True,
)

feed_page = st.Page(
    "pages/2_Transaction_Feed.py",
    title="Transaction Feed",
    icon="💳",
)

pg = st.navigation([queue_page, feed_page])
pg.run()
