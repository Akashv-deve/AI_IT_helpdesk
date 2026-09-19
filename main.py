#!/usr/bin/env python3
"""Zero-install entry point.

``pip install -e .`` is the tidy way to run this project, but pressing F5 in
VS Code on a freshly cloned repo should also just work. This shim puts ``src``
on the import path and hands over to the real CLI.

    python main.py
    python main.py demo
    python main.py ask "my vpn keeps dropping"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from helpdesk.cli import main  # noqa: E402  (import must follow the path tweak)

if __name__ == "__main__":
    sys.exit(main())
