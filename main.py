"""Entry point for the native Windows application."""

import os
from pathlib import Path

from dotenv import load_dotenv

from jarvis_dev.ui import run_app


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
root_value = os.getenv("WORKSPACE_ROOT", "workspace")
workspace_root = Path(root_value)
if not workspace_root.is_absolute():
    workspace_root = BASE_DIR / workspace_root

if __name__ == "__main__":
    raise SystemExit(run_app(workspace_root))
