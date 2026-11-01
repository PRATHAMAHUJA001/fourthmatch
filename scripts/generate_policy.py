#!/usr/bin/env python3
"""Generate data/policy/receiving_policy.md — one-off, NOT part of seeding.

Every clause's prose is rewritten by BULK_MODEL (Meta Responses API, shapes
from docs/MODEL_NOTES.md §2 via app.infra.meta.client.MetaModelClient, model
ID from core/config only). Structure, clause numbers and every number come
from backend/app/seed/policy_template.py and never from the model.

After each rewrite, Python verifies that every number extracted from the new
prose equals the template clause's number set; a mismatched clause is
regenerated (max 3 attempts), then falls back to the canonical template text.
The finished file is verified whole (check_policy) before it is written.
Seeding only ever verifies this committed file and refuses on mismatch.

Usage: PYTHONPATH=backend backend/.venv/bin/python scripts/generate_policy.py [--clause 4.2]

With --clause, only that clause is regenerated; every other clause keeps the
prose already committed in data/policy/receiving_policy.md.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings, load_model_config  # noqa: E402
from app.domain.schemas.seed import ClauseRewrite  # noqa: E402
from app.infra.db.session import create_all, make_engine, make_session_factory  # noqa: E402
from app.infra.meta.client import MetaModelClient  # noqa: E402
from app.seed.policy_template import (  # noqa: E402
    CLAUSES,
    check_policy,
    extract_numbers,
    parse_clauses,
    render_policy_with,
)

OUT = ROOT / "data" / "policy" / "receiving_policy.md"
DB = ROOT / "data" / "fourthmatch.db"
MAX_ATTEMPTS = 3


async def rewrite_clause(client: MetaModelClient, session, clause, *, model: str) -> tuple[str, bool]:  # type: ignore[no-untyped-def]
    """Return (prose, used_model). Falls back to canonical text after retries."""
    numbers = ("; ".join(f"{k}={v}" for k, v in clause.numbers.items())
               if clause.numbers else "none — the rewrite must contain no digits, percentages or amounts")
    prompt = (
        "Rewrite the following company policy clause in clear formal policy prose, "
        "one paragraph, preserving the meaning exactly. You must preserve every number "
        "exactly as written (digits, percentages, rupee amounts, day counts) and must not "
        "add or remove any number. Do not do arithmetic. "
        f"Clause id: {clause.id}\nRequired numbers: {numbers}\nClause text:\n{clause.text}"
    )
    for _ in range(MAX_ATTEMPTS):
        result = await client.call_model(
            purpose="policy_clause_rewrite", model=model,
            prompt=prompt, output_schema=ClauseRewrite, session=session)
        if result.clause_id != clause.id:
            continue
        prose = result.prose.strip()
        if extract_numbers(prose) == clause.number_set:
            return prose, True
    return clause.text, False


async def amain(only_clause: str | None = None) -> int:
    config = load_model_config()
    engine = make_engine(DB)
    create_all(engine)
    session = make_session_factory(engine)()
    client = MetaModelClient(config)
    # Single-clause mode: start from the committed prose so untouched
    # clauses render byte-identically; only the named clause is rewritten.
    prose_by_id: dict[str, str] = parse_clauses(OUT.read_text()) if only_clause and OUT.exists() else {}
    fallbacks: list[str] = []
    try:
        for clause in CLAUSES:
            if only_clause and clause.id != only_clause:
                continue
            prose, used_model = await rewrite_clause(client, session, clause, model=config.bulk_model)
            prose_by_id[clause.id] = prose
            if not used_model:
                fallbacks.append(clause.id)
            print(f"  clause {clause.id}: {'rewritten' if used_model else 'CANONICAL FALLBACK'}")
    finally:
        session.close()
    text = render_policy_with(prose_by_id)
    check = check_policy(text)
    if not check.ok:
        raise SystemExit(f"generated policy failed verification: {check}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    changed = not OUT.exists() or OUT.read_text() != text
    if changed:
        OUT.write_text(text)
    print(f"policy: {OUT} ({len(CLAUSES)} clauses, {len(fallbacks)} canonical fallbacks"
          f"{': ' + ','.join(fallbacks) if fallbacks else ''}){' (file updated)' if changed else ' (unchanged)'}")
    print(f"model: BULK_MODEL={get_settings().bulk_model} (from .env via core/config)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clause", default=None,
                        help="regenerate only this clause id (e.g. 4.2); others keep committed prose")
    args = parser.parse_args()
    if args.clause and args.clause not in {c.id for c in CLAUSES}:
        parser.error(f"unknown clause id: {args.clause}")
    raise SystemExit(asyncio.run(amain(args.clause)))
