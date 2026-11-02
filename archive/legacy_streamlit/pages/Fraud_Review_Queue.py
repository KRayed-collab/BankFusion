"""
BankFusion Page 1: Fraud Review Queue (Module & Page)
"""

import sys
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def render():
    mod = importlib.import_module("pages.1_Fraud_Review_Queue")
    mod.run_queue_page()

if __name__ == "__main__":
    render()
