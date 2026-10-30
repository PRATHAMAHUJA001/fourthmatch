#!/usr/bin/env python3
"""Execute `python -m app.seed` via runpy (same __main__ entrypoint)."""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.argv = ["app.seed", *sys.argv[1:]]
try:
    runpy.run_module("app.seed", run_name="__main__")
except SystemExit as exc:
    raise SystemExit(exc.code) from None
