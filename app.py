#!/usr/bin/env python3
"""Web entry point.

    streamlit run app.py

Puts ``src`` on the import path so a freshly cloned repository runs without
``pip install -e .`` first, then hands over to the application shell. All logic
lives in ``src/web`` and ``src/helpdesk``; this file is only a launcher.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from web.runner import run  # noqa: E402  (import must follow the path tweak)

run()
