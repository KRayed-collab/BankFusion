"""
BankFusion Background Worker: Transaction Feed Loader
======================================================
Queries the Kimball Star Schema data warehouse and constructs the enriched
transaction feed DataFrame asynchronously using a dedicated QThread and an
isolated SQLAlchemy session.
"""

from typing import Optional
from PySide6.QtCore import QThread, Signal
import pandas as pd

from database.database_connection import SessionLocal
from warehouse.warehouse_queries import get_transaction_feed_dataframe


class FeedLoaderWorker(QThread):
    """
    Background worker for loading transaction feed data off the main UI thread.
    Emits feed_loaded(pd.DataFrame) on success, or feed_failed(str) on error.
    """

    feed_loaded = Signal(object)  # pd.DataFrame
    feed_failed = Signal(str)     # Error description

    def __init__(self, limit: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.limit = limit

    def run(self):
        try:
            # Use dedicated, isolated SQLAlchemy session for this thread
            with SessionLocal() as session:
                df = get_transaction_feed_dataframe(session, limit=self.limit)

            self.feed_loaded.emit(df)
        except Exception as e:
            self.feed_failed.emit(str(e))

