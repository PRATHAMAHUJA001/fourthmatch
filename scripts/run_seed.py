#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.seed.generate import main

raise SystemExit(main(sys.argv[1:]))
