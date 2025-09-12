"""
Ensure the project's `src/` directory is on `sys.path` so imports like
`import src.api...` work from any entrypoint (pytest, scripts, REPL).
"""

from __future__ import annotations

import os
import sys

# Project root is the directory containing this file
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

# Put src/ on sys.path if not present
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
