"""
BankFusion Database Connection Manager
======================================
Manages SQLAlchemy engine creation, thread-safe session factories, and database paths.
Defaults to local SQLite: 'bankfusion.db'.
In PyInstaller frozen mode, places database in writable %APPDATA%/BankFusion/ to ensure persistence.
"""

import sys
import os
import shutil
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Persistent database path resolution
if getattr(sys, "frozen", False):
    # Running as a compiled Windows .exe
    app_data_dir = Path(os.getenv("APPDATA", str(PROJECT_ROOT))) / "BankFusion"
    app_data_dir.mkdir(parents=True, exist_ok=True)
    DEFAULT_DB_PATH = app_data_dir / "bankfusion.db"

    # Seed initial DB from bundle if not already in APPDATA
    if not DEFAULT_DB_PATH.exists():
        candidates = []
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            candidates.append(Path(bundle_dir) / "bankfusion.db")
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "_internal" / "bankfusion.db")
        candidates.append(exe_dir / "bankfusion.db")

        for bundled_db in candidates:
            if bundled_db.exists():
                try:
                    shutil.copy2(bundled_db, DEFAULT_DB_PATH)
                    break
                except Exception:
                    pass
else:
    DEFAULT_DB_PATH = PROJECT_ROOT / "bankfusion.db"

# Format as POSIX path to avoid backslash escaping issues in SQLite URL
DEFAULT_DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.as_posix()}")

# SQLAlchemy Declarative Base
Base = declarative_base()


def get_engine(db_url: str = None):
    """
    Creates and returns a SQLAlchemy engine.
    For SQLite, enforces foreign key constraint checking (PRAGMA foreign_keys = ON).
    """
    url = db_url or DEFAULT_DB_URL
    is_sqlite = url.startswith("sqlite")

    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(url, connect_args=connect_args, echo=False)

    if is_sqlite:
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return engine


# Default global engine and session factory
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_session():
    """Context manager or generator for database sessions."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
