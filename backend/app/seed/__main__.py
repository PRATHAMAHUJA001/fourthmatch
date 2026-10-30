"""Run as: PYTHONPATH=backend backend/.venv/bin/python -m app.seed"""
from app.seed.generate import main

if __name__ == "__main__":
    raise SystemExit(main())
