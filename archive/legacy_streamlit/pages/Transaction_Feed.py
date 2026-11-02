"""
BankFusion Page 2: Transaction Feed (Module & Page)
"""

import sys
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def render():
    mod = importlib.import_module("pages.2_Transaction_Feed")
    mod.run_feed_page()

if __name__ == "__main__":
    render()

