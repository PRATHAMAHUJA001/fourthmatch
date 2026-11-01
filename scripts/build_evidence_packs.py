#!/usr/bin/env python3
"""Build evidence packs (PDF + JSON, debit note for partial_pay) for deliveries.

Usage (from repo root):
  PYTHONPATH=backend backend/.venv/bin/python scripts/build_evidence_packs.py [--delivery-id N ...]

Defaults to every delivery in the DB (the four scenario deliveries after
`python -m app.seed`). Reads the DB and storage root from the usual config
(DATABASE_URL / STORAGE_ROOT). No model calls.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import REPO_ROOT, get_settings  # noqa: E402
from app.domain.money import format_inr  # noqa: E402
from app.domain.schemas.evidence import PackModels  # noqa: E402
from app.infra.db.models.purchasing import Delivery  # noqa: E402
from app.infra.db.repositories.cases import SqlCaseRepository  # noqa: E402
from app.infra.db.repositories.evidence import SqlEvidenceRepository  # noqa: E402
from app.infra.db.session import create_all, make_engine, make_session_factory  # noqa: E402
from app.infra.frames import VideoFrameSource  # noqa: E402
from app.infra.pdf import ReportLabRenderer  # noqa: E402
from app.infra.storage import LocalFileStore  # noqa: E402
from app.services.cases import CaseService  # noqa: E402
from app.services.evidence import EvidenceService  # noqa: E402
from app.services.policy_docs import PolicyDocService  # noqa: E402

DEFAULT_POLICY = REPO_ROOT / "data" / "policy" / "receiving_policy.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build FourthMatch evidence packs.")
    parser.add_argument("--delivery-id", type=int, nargs="*", help="deliveries to build (default: all)")
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = make_engine()
    create_all(engine)
    session = make_session_factory(engine)()
    try:
        store = LocalFileStore(settings.storage_root)
        service = EvidenceService(
            CaseService(SqlCaseRepository(session)),
            SqlEvidenceRepository(session),
            store,
            ReportLabRenderer(),
            VideoFrameSource(settings.storage_root, REPO_ROOT, settings.sam_proxy_fps),
            PackModels(
                perception_model=settings.perception_model,
                decision_model=settings.decision_model,
                compiler_model=settings.compiler_model,
                seg_model=settings.seg_model,
            ),
            policy_provider=PolicyDocService(store, DEFAULT_POLICY).current,
        )
        ids = args.delivery_id or [d.id for d in session.query(Delivery).order_by(Delivery.id).all()]
        if not ids:
            print("No deliveries found. Run `python -m app.seed` first.")
            return 1
        failures = 0
        print(f"{'delivery':<9} {'verdict':<12} {'held':>12}  {'verified':<8} sha256 / files")
        for delivery_id in ids:
            try:
                pack = service.build_pack(delivery_id)
                case_po = SqlEvidenceRepository(session).get_delivery(delivery_id)
                case = CaseService(SqlCaseRepository(session)).get_case(case_po.po_id) if case_po else None
                verdict = case.verdict.value if case and case.verdict else "-"
                held = format_inr(case.held_paise) if case else "-"
                print(f"{delivery_id:<9} {verdict:<12} {held:>12}  {str(pack.verified):<8} {pack.sha256}")
                print(f"{'':<9} files: {', '.join(pack.files)}")
            except Exception as exc:  # noqa: BLE001 - report and continue with the next delivery
                failures += 1
                print(f"{delivery_id:<9} FAILED: {type(exc).__name__}: {exc}")
        print(f"\nstorage: {settings.storage_root / 'evidence'}")
        return 1 if failures else 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
