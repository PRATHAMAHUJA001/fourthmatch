#!/usr/bin/env python3
"""Generate the synthetic eval-image set and record SAM counts for it.

12 top-down CCTV-style stills from IMAGE_MODEL with prompted counts 3..14 (mix of
"cardboard box" and "white sack"). Each is then run through SEG_MODEL with the
matching noun phrase; sam_count = distinct SAM boxes at or above SAM_SCORE_MIN,
counted in Python. Outputs in data/eval_images/: imgNN.png, labels.json
(validated by EvalImageLabel; true_count stays null until a human confirms with
scripts/confirm_eval_images.py) and grid.html.

SYNTHETIC test scenes only, never evidence. Idempotent: images that already
exist are not regenerated, SAM raw output is cached by image SHA-256 under
storage/cache/sam, and an existing true_count is never overwritten.

Needs MODEL_API_KEY and the model IDs in .env; exits 2 without them (only when
there is work to do). `--grid-only` rebuilds grid.html and needs no key.

Usage: backend/.venv/bin/python scripts/gen_eval_images.py [--grid-only]
"""
from __future__ import annotations

import argparse
import asyncio
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.errors import AppError  # noqa: E402
from app.domain.eval_images import EVAL_IMAGE_PLAN, build_prompt, count_boxes, image_id, render_grid_html  # noqa: E402
from app.domain.schemas.eval import EvalImageLabel  # noqa: E402
from app.infra.db.session import make_engine, make_session_factory  # noqa: E402
from app.infra.meta.client import MetaModelClient  # noqa: E402
from app.infra.meta.sam import SamSegmenter  # noqa: E402
from app.services.eval_files import load_labels, save_labels  # noqa: E402

OUT_DIR = ROOT / "data" / "eval_images"


def _write_outputs(labels: list[EvalImageLabel]) -> None:
    save_labels(OUT_DIR / "labels.json", labels)
    (OUT_DIR / "grid.html").write_text(render_grid_html(labels), encoding="utf-8")


def _to_png(raw: bytes) -> bytes:
    """The API may send WEBP bytes (MODEL_NOTES §7): always store a genuine PNG."""
    img = Image.open(io.BytesIO(raw))
    img.load()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grid-only", action="store_true", help="rebuild grid.html from labels.json, no model calls")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = {lb.id: lb for lb in load_labels(OUT_DIR / "labels.json")}
    plan = [(image_id(i + 1), count, phrase) for i, (count, phrase) in enumerate(EVAL_IMAGE_PLAN)]

    def done(img_id: str) -> bool:
        lb = existing.get(img_id)
        return lb is not None and lb.sam_count is not None and (OUT_DIR / lb.file).exists()

    pending = [p for p in plan if not done(p[0])]
    ordered = [existing[i] for i, _, _ in plan if i in existing]
    if args.grid_only:
        _write_outputs(ordered)
        print(f"grid.html rebuilt for {len(ordered)} images -> {OUT_DIR.relative_to(ROOT)}/grid.html")
        return 0
    if not pending:
        _write_outputs(ordered)
        print("All 12 eval images already generated; nothing to do.")
        return 0

    settings = get_settings()
    if not settings.model_api_key:
        print("MODEL_API_KEY is not set (put it in .env). Cannot generate eval images.", file=sys.stderr)
        return 2
    try:
        config = settings.model_config_model()
    except ValueError as exc:
        print(f"Model configuration incomplete: {exc}", file=sys.stderr)
        return 2

    factory = make_session_factory(make_engine())
    session = factory()
    client = MetaModelClient(config)
    segmenter = SamSegmenter(config, settings.cache_root)
    failures = 0
    print(f"{'id':<6} {'phrase':<14} {'prompted':>8} {'sam':>4}  note")
    try:
        for img_id, count, phrase in plan:
            if done(img_id):
                lb = existing[img_id]
                print(f"{img_id:<6} {phrase:<14} {count:>8} {lb.sam_count:>4}  skipped (already done)")
                continue
            path = OUT_DIR / f"{img_id}.png"
            prompt = build_prompt(count, phrase)
            try:
                note = "reused file"
                if not path.exists():
                    raw = await client.generate_image(
                        purpose="eval_image_generation", model=config.image_model, prompt=prompt, session=session)
                    path.write_bytes(_to_png(raw))
                    note = "generated"
                seg = await segmenter.segment_image(
                    image_bytes=path.read_bytes(), mime="image/png", phrase=phrase, session=session)
                sam_count = count_boxes([(b.object_id, b.confidence) for b in seg.boxes], settings.sam_score_min)
                note += ", sam cache hit" if seg.cache_hit else ", sam called"
            except (AppError, OSError, ValueError) as exc:
                failures += 1
                print(f"{img_id:<6} {phrase:<14} {count:>8} {'-':>4}  FAILED: {type(exc).__name__}: {exc}")
                prior = existing.get(img_id)
                if path.exists():  # keep the picture; SAM is retried on the next run
                    existing[img_id] = prior or EvalImageLabel(
                        id=img_id, file=path.name, prompt=prompt, phrase=phrase, prompted_count=count)
                    _write_outputs([existing[i] for i, _, _ in plan if i in existing])
                continue
            prior = existing.get(img_id)
            existing[img_id] = EvalImageLabel(
                id=img_id, file=path.name, prompt=prompt, phrase=phrase, prompted_count=count,
                sam_count=sam_count, true_count=prior.true_count if prior else None)
            _write_outputs([existing[i] for i, _, _ in plan if i in existing])
            print(f"{img_id:<6} {phrase:<14} {count:>8} {sam_count:>4}  {note}")
    finally:
        session.close()

    print(f"\n{sum(1 for i, _, _ in plan if done(i))}/12 complete -> {OUT_DIR.relative_to(ROOT)}/labels.json, grid.html")
    print("Next: open data/eval_images/grid.html, count each picture yourself, then run\n"
          "  backend/.venv/bin/python scripts/confirm_eval_images.py img01=<n> img02=<n> ...")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
