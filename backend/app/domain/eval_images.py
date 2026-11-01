"""Pure helpers for the synthetic eval-image set: the plan, prompts, box counting, grid page.

The image model is told a count but does not obey it exactly, so the prompted
count is never ground truth: a human confirms ``true_count`` from the picture.
"""

from __future__ import annotations

import html
from collections.abc import Sequence

from app.domain.schemas.eval import EvalImageLabel

PHRASE_BOX = "cardboard box"
PHRASE_SACK = "white sack"
PLURAL = {PHRASE_BOX: "cardboard boxes", PHRASE_SACK: "white sacks"}

# (prompted_count, phrase): counts spread 3..14, both phrases interleaved.
EVAL_IMAGE_PLAN: tuple[tuple[int, str], ...] = (
    (3, PHRASE_BOX), (4, PHRASE_SACK), (5, PHRASE_BOX), (6, PHRASE_BOX),
    (7, PHRASE_SACK), (8, PHRASE_BOX), (9, PHRASE_SACK), (10, PHRASE_BOX),
    (11, PHRASE_SACK), (12, PHRASE_SACK), (13, PHRASE_BOX), (14, PHRASE_SACK),
)


def image_id(index: int) -> str:
    """1-based: img01 .. img12."""
    return f"img{index:02d}"


def build_prompt(count: int, phrase: str) -> str:
    plural = PLURAL.get(phrase, f"{phrase}s")
    return (
        f"Top-down CCTV camera view of a warehouse receiving dock floor with exactly {count} {plural} "
        "placed apart from each other on the concrete floor, every one fully visible and not stacked, "
        "fixed overhead security camera angle, flat even lighting, no people, no text overlays"
    )


def count_boxes(boxes: Sequence[tuple[str, float | None]], score_min: float) -> int:
    """Distinct SAM object ids whose confidence is at least ``score_min``.

    ``boxes`` is (object_id, confidence). A missing confidence is accepted
    (same rule as track counting in domain/counting.py). Counting happens here,
    in Python; the model never counts.
    """
    return len({oid for oid, conf in boxes if conf is None or conf >= score_min})


def _fmt(value: int | None) -> str:
    return "—" if value is None else str(value)


def render_grid_html(labels: Sequence[EvalImageLabel]) -> str:
    """Static page: each image with prompted / SAM / confirmed counts and the CLI hint."""
    cards: list[str] = []
    for lb in labels:
        cards.append(
            f"""<figure>
<img src="{html.escape(lb.file)}" alt="{html.escape(lb.id)}" loading="lazy">
<figcaption>
<b>{html.escape(lb.id)}</b> <span class="tag">SYNTHETIC</span><br>
phrase: <code>{html.escape(lb.phrase)}</code><br>
prompted: <b>{lb.prompted_count}</b> &nbsp; SAM: <b>{_fmt(lb.sam_count)}</b> &nbsp; confirmed: <b>{_fmt(lb.true_count)}</b><br>
<label>your count <input size="3" placeholder="{html.escape(lb.id)}=?" aria-label="true count for {html.escape(lb.id)}"></label>
</figcaption>
</figure>"""
        )
    hint = " ".join(f"{lb.id}=N" for lb in labels[:2]) or "img01=N"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FourthMatch eval images</title>
<style>
body{{font:14px/1.4 system-ui,sans-serif;margin:16px;background:#fafafa;color:#16171a}}
h1{{font-size:18px;margin:0 0 4px}} p{{margin:0 0 12px;max-width:70ch}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}}
figure{{margin:0;background:#fff;border:1px solid #d8d8dc;border-radius:6px;padding:8px}}
img{{width:100%;height:auto;display:block;border-radius:4px}}
figcaption{{margin-top:8px;font-variant-numeric:tabular-nums}}
.tag{{font-size:11px;border:1px solid #888;border-radius:4px;padding:0 4px}}
code{{background:#eee;padding:0 3px;border-radius:3px}}
</style></head><body>
<h1>Eval images <span class="tag">SYNTHETIC</span></h1>
<p>Count the {html.escape(PHRASE_BOX)}es / {html.escape(PHRASE_SACK)}s you can see in each picture yourself. The prompted count is only what the
image model was asked for. Then run, from the repo root:
<code>backend/.venv/bin/python scripts/confirm_eval_images.py {html.escape(hint)} ...</code></p>
<div class="grid">
{chr(10).join(cards)}
</div></body></html>
"""
