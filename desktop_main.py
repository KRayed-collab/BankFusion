"""
BankFusion: Multi-Bank Data Warehouse & Fraud Analytics Platform
================================================================
Native Desktop Application Entrypoint (PySide6 / Qt 6)
No web browsers, no localhost servers, no embedded HTML.
Runs natively as a conventional Windows desktop program.
"""

import sys
import os
from pathlib import Path

# Ensure project root is in Python module search path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from database.database_connection import SessionLocal, engine, DEFAULT_DB_PATH
from database.database_models import Base, DimBank, DimTime
from data_generation.generate_ground_truth import generate_and_load_full_source_data
from etl.run_etl_pipeline import execute_full_etl_pipeline
from fraud_detection.save_detection_results import execute_fraud_detection_run
from ui.main_window import MainWindow


def ensure_database_ready():
    """
    Ensures that the SQLite database exists and has seed data.
    If database file is empty or missing dimensions, runs initialization.
    """
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        bank_count = session.query(DimBank).count()
        time_count = session.query(DimTime).count()

        if bank_count == 0 or time_count == 0:
            print("[INFO] Initializing BankFusion SQLite Database with base seeds...")
            generate_and_load_full_source_data(random_seed=42, reset_tables=False)
            execute_full_etl_pipeline()
            execute_fraud_detection_run(session)


def main():
    # 1. Enable high-DPI scaling
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    # 2. Initialize Qt Application
    app = QApplication(sys.argv)
    app.setApplicationName("BankFusion")
    app.setOrganizationName("BankFusion Analytics")

    # 3. Verify SQLite Database readiness
    ensure_database_ready()

    # 4. Construct and display Main Window
    window = MainWindow()
    window.show()

    # 5. Clean Event Loop Exit
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

