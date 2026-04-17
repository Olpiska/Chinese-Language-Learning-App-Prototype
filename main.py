import sys
import os
from pathlib import Path

# Force UTF-8 output on Windows to avoid Turkish/other locale codec errors
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # type: ignore
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')  # type: ignore

# ── Load .env file before anything else ──────────────────────
# This sets OPENAI_API_KEY, OPENAI_BASE_URL, AI_MODEL in the environment
try:
    from dotenv import load_dotenv
    from utils.config import get_base_dir
    env_path = get_base_dir() / ".env"
    load_dotenv(dotenv_path=env_path)
    if os.environ.get("OPENAI_API_KEY"):
        print("[main] .env loaded - AI Tutor will use real API.")
    else:
        print("[main] No API key found in .env - AI Tutor running in simulated mode.")
except ImportError:
    print("[main] python-dotenv not installed; skipping .env load.")

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from utils.config import get_base_dir

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Initialize the main window (it reads env vars to configure the AI tutor)
    window = MainWindow()
    window.show()

    # Start the Qt event loop
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
