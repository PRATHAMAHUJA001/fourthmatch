#!/usr/bin/env python3
"""Populate the compiler cache for the committed policy (one live run).

Compiles data/policy/receiving_policy.md clause-by-clause with COMPILER_MODEL
via PolicyCompilerService.compile_draft (in-memory only: nothing persisted,
nothing approved). Raw outputs land in storage/cache keyed by clause SHA-256
+ model + COMPILER_PROMPT_VERSION, so tests/test_accuracy.py can score the
model-compiled rules offline.

Usage: PYTHONPATH=backend backend/.venv/bin/python scripts/compile_policy_cache.py
Re-running is cheap: unchanged clauses are cache hits.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.infra.cache import Sha256Cache  # noqa: E402
from app.infra.db.repositories.policies import SqlRuleRepository  # noqa: E402
from app.infra.db.session import make_engine, make_session_factory  # noqa: E402
from app.infra.meta.client import MetaModelClient  # noqa: E402
from app.services.policy_compiler import PolicyCompilerService  # noqa: E402

POLICY_PATH = ROOT / "data" / "policy" / "receiving_policy.md"


async def main() -> None:
    settings = get_settings()
    cache = Sha256Cache(settings.cache_root)
    client = MetaModelClient(settings.model_config_model(), cache=cache)
    # compile_draft never touches the repository; a scratch session satisfies the ctor.
    session = make_session_factory(make_engine(":memory:"))()
    service = PolicyCompilerService(
        SqlRuleRepository(session), client, settings.compiler_model, session=None, cache=cache
    )
    markdown = POLICY_PATH.read_text()
    draft = await service.compile_draft(markdown)
    print(
        f"clauses={draft.clauses_seen} compiled(new model calls)={draft.compiled} "
        f"cache_hits={draft.cache_hits} retries={draft.retries} skipped_non_rule={draft.skipped_non_rule} "
        f"invalid={draft.invalid} ambiguous={draft.ambiguous}"
    )
    for route in draft.approver_routes:
        print(f"ROUTE clause={route.source_clause} role={route.role!r} "
              f"band_inr={route.min_value_inr}..{route.max_value_inr}")
    for item in draft.rules:
        r = item.rule
        print(
            f"RULE {r.rule_id} clause={r.source_clause} {r.condition.field}"
            f"{r.condition.op}{r.condition.value} "
            f"action={r.action} cat={r.goods_category!r} errors={item.validation_errors}"
        )
    session.close()


if __name__ == "__main__":
    asyncio.run(main())
