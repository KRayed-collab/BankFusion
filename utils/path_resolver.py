"""
BankFusion Path Resolver
========================
Provides robust, frozen-aware filesystem path resolution for config files,
assets, and databases across both source execution and compiled PyInstaller bundles.
Handles Windows spaces in paths and _internal / sys._MEIPASS extraction structures.
"""

import sys
import os
from pathlib import Path

# Resolve base project directory from file location
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_project_root() -> Path:
    """Returns the effective project root directory."""
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir and Path(bundle_dir).exists():
            return Path(bundle_dir)
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "_internal").exists():
            return exe_dir / "_internal"
        return exe_dir
    return PROJECT_ROOT


def get_config_path(filename: str) -> Path:
    """
    Locates a configuration file, searching:
    1. PyInstaller bundle directory (sys._MEIPASS / 'config' / filename)
    2. PyInstaller _internal directory (exe_dir / '_internal' / 'config' / filename)
    3. Executable adjacent directory (exe_dir / 'config' / filename)
    4. Development workspace directory (PROJECT_ROOT / 'config' / filename)
    """
    candidates = []

    # 1. sys._MEIPASS (onefile or onedir runtime hook)
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(Path(bundle_dir) / "config" / filename)
        candidates.append(Path(bundle_dir) / filename)

    # 2. PyInstaller _internal or exe adjacent directory
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "_internal" / "config" / filename)
        candidates.append(exe_dir / "_internal" / filename)
        candidates.append(exe_dir / "config" / filename)
        candidates.append(exe_dir / filename)

    # 3. Development root
    candidates.append(PROJECT_ROOT / "config" / filename)
    candidates.append(PROJECT_ROOT / filename)

    # Return the first candidate that exists
    for p in candidates:
        try:
            if p.exists():
                return p.resolve()
        except Exception:
            pass

    # Fallback to standard dev path
    return (PROJECT_ROOT / "config" / filename).resolve()

