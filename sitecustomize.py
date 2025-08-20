"""
sitecustomize.py
----------------
Ensures the project's `src/` directory is on `sys.path` early so imports like `import src.api...`
work in any entrypoint (pytest, scripts, interactive shells).

Also normalizes the PYTHONPATH environment variable to include `src/` only once.
"""
from __future__ import annotations

import os
import sys

# Project root is the directory containing this file
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

# 1) Put src/ on sys.path if not present
if SRC_DIR not in sys.path:
  sys.path.insert(0, SRC_DIR)

# 2) Normalize PYTHONPATH to include src/ once (and only once)
existing = os.environ.get("PYTHONPATH", "")
parts = [p for p in existing.split(os.pathsep) if p] if existing else []
if SRC_DIR not in parts:
  parts.insert(0, SRC_DIR)
# remove duplicates while keeping order
seen = set()
normalized = [p for p in parts if not (p in seen or seen.add(p))]
os.environ["PYTHONPATH"] = os.pathsep.join(normalized)

# Note: This project uses FastAPI, not Django. Avoid setting DJANGO_SETTINGS_MODULE here
# to prevent accidental cross-framework configuration in environments where Django might
# also be installed.