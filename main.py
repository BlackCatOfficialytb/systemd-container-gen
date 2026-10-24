#!/usr/bin/env python3
"""Launch the local systemd-container-gen build tool."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cli import main as cli_main
from tools.gui import main as gui_main, is_available as gui_available
from tools.tui import run as tui_run


def main() -> int:
    if len(sys.argv) > 1:
        return cli_main()
    if gui_available():
        return gui_main()
    return tui_run()


if __name__ == "__main__":
    sys.exit(main())
