"""
BankFusion Worker: Fraud Detection Background Worker
====================================================
Executes the complete 4-factor deterministic screening run asynchronously
using a dedicated QThread and isolated SQLAlchemy session.
"""

from PySide6.QtCore import QThread, Signal
from database.database_connection import SessionLocal
from fraud_detection.save_detection_results import execute_fraud_detection_run


class DetectionWorker(QThread):
    """Background worker for non-blocking fraud screening runs."""

    # Emitted with the standardized detection result dictionary
    detection_completed = Signal(dict)
    detection_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            with SessionLocal() as session:
                result = execute_fraud_detection_run(session)

            if result.get("success", False):
                self.detection_completed.emit(result)
            else:
                self.detection_failed.emit(result.get("error_message", "Unknown error occurred during screening."))
        except Exception as e:
            self.detection_failed.emit(str(e))

