#!/usr/bin/env python3
"""Record the human-confirmed true_count for synthetic eval images.

Look at data/eval_images/grid.html, count the objects in each picture yourself,
then: backend/.venv/bin/python scripts/confirm_eval_images.py img01=7 img02=5
No model calls, no key needed. All arguments are validated before anything is
written. Run with no arguments to list the current state.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.eval_images import render_grid_html  # noqa: E402
from app.services.eval_files import load_labels, save_labels  # noqa: E402

OUT_DIR = ROOT / "data" / "eval_images"


def _show(labels: list) -> None:  # type: ignore[type-arg]
    print(f"{'id':<6} {'phrase':<14} {'prompted':>8} {'sam':>4} {'true':>5}")
    for lb in labels:
        sam = "-" if lb.sam_count is None else lb.sam_count
        true = "-" if lb.true_count is None else lb.true_count
        print(f"{lb.id:<6} {lb.phrase:<14} {lb.prompted_count:>8} {sam:>4} {true:>5}")
    left = [lb.id for lb in labels if lb.true_count is None]
    print(f"\n{len(labels) - len(left)}/{len(labels)} confirmed" + (f"; still unconfirmed: {' '.join(left)}" if left else ""))


def main(argv: list[str]) -> int:
    path = OUT_DIR / "labels.json"
    labels = load_labels(path)
    if not labels:
        print("data/eval_images/labels.json is missing or empty; run scripts/gen_eval_images.py first.", file=sys.stderr)
        return 1
    by_id = {lb.id: lb for lb in labels}
    updates: dict[str, int] = {}
    for arg in argv:
        key, sep, value = arg.partition("=")
        if not sep or key not in by_id or not value.isdigit():
            print(f"Bad argument {arg!r}: expected <id>=<non-negative integer> with id in "
                  f"{labels[0].id}..{labels[-1].id}.", file=sys.stderr)
            return 1
        updates[key] = int(value)
    for key, value in updates.items():
        by_id[key].true_count = value
    if updates:
        save_labels(path, labels)
        (OUT_DIR / "grid.html").write_text(render_grid_html(labels), encoding="utf-8")
        print(f"Updated {len(updates)} image(s).\n")
    _show(labels)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
