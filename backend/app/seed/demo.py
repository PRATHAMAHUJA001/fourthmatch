"""Load the 4 manifest scenarios into a demo-ready state WITHOUT any model call.

    PYTHONPATH=backend backend/.venv/bin/python -m app.seed --demo

What it does (idempotent; running twice changes nothing):
  1. Runs the normal seed (vendors, POs, GRNs, invoices, the 4 video deliveries).
  2. Perception rows: copied from the committed eval output data/eval_counts.json
     (observed_count, max_visible, evidence_quality, damaged_track_ids, reasons).
     Those numbers were produced by the real SAM pipeline on Pratham's Mac; this
     loader only imports them. A line that already has a perception row (e.g. from
     a real run) is never touched.
  3. Approved compiled rules, from the first source that exists:
       a. data/demo/snapshot.json   (committed export, scripts/export_demo_snapshot.py)
       b. the compiler cache under storage/cache (only exists where
          scripts/compile_policy_cache.py ran; storage/ is gitignored)
     Neither exists on a fresh server => rules are NOT loaded and the report says so
     loudly. Nothing is invented: without approved rules the case pages cannot show
     real verdicts. Fix: run scripts/export_demo_snapshot.py on the Mac and commit
     data/demo/snapshot.json.
  4. Tracks (so the case page can list SAM track ids): only from the snapshot.

Expected counts / verdicts are never written here; verdicts are recomputed by
the case service from perception + approved rules.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT, Settings
from app.domain.enums import RuleStatus
from app.domain.rules import _norm_category, validate_rule
from app.domain.schemas.policies import ClauseClassification, CompileClauseOutput, CompiledRule
from app.infra.cache import Sha256Cache, cache_key_for, sha256_hex
from app.infra.db.models import Delivery, PerceptionResult, PurchaseOrder, Rule, SamRun, Track
from app.infra.db.session import make_engine, make_session_factory
from app.seed.generate import seed
from app.services.policy_compiler import (
    COMPILER_PROMPT_VERSION,
    clause_rule_errors,
    policy_version_of,
    retry_cache_key,
    split_clauses,
)

EVAL_COUNTS_PATH = REPO_ROOT / "data" / "eval_counts.json"
SNAPSHOT_PATH = REPO_ROOT / "data" / "demo" / "snapshot.json"
SCENARIO_DIR = REPO_ROOT / "samples" / "scenarios"
IMPORTED_STATUS = "imported"


@dataclass
class DemoReport:
    perception_rows: int = 0
    perception_skipped_existing: int = 0
    perception_missing_lines: list[str] = field(default_factory=list)
    rules_loaded: int = 0
    rules_source: str = "none"
    tracks_loaded: int = 0
    warnings: list[str] = field(default_factory=list)


def rules_from_compiler_cache(settings: Settings, policy_markdown: str) -> list[CompiledRule] | None:
    """Rebuild the compiled rules from the on-disk compiler cache only; None if incomplete.

    Mirrors PolicyCompilerService._compile_clauses (two-step cache + one retry entry)
    but can never call a model: it only reads cache files.
    """
    if not settings.compiler_model:
        return None
    cache_root = settings.cache_root
    if not cache_root.is_dir():
        return None
    cache = Sha256Cache(cache_root)
    rules: list[CompiledRule] = []
    seen: set[str] = set()
    for clause in split_clauses(policy_markdown):
        digest = sha256_hex(clause.text.encode())
        cls_raw = cache.get_json(
            cache_key_for("policy_classify", COMPILER_PROMPT_VERSION, settings.compiler_model, digest))
        if cls_raw is None:
            return None
        if ClauseClassification.model_validate(cls_raw).kind != "payment_rule":
            continue
        raw = cache.get_json(
            cache_key_for("policy_compile", COMPILER_PROMPT_VERSION, settings.compiler_model, digest))
        if raw is None:
            return None
        clause_rules = CompileClauseOutput.model_validate(raw).rules
        errors = [e for errs in clause_rule_errors(clause, clause_rules) for e in errs]
        if errors:
            retry_raw = cache.get_json(retry_cache_key(settings.compiler_model, clause, clause_rules, errors))
            if retry_raw is not None and CompileClauseOutput.model_validate(retry_raw).rules:
                clause_rules = CompileClauseOutput.model_validate(retry_raw).rules
        for rule in clause_rules:
            if rule.source_clause != clause.clause_id:
                continue
            rule_id = rule.rule_id.strip() or f"clause-{clause.clause_id}"
            if rule_id in seen:
                rule_id = f"{rule_id}#{clause.clause_id}"
            seen.add(rule_id)
            rule = rule.model_copy(update={"rule_id": rule_id})
            if not validate_rule(rule):
                rules.append(rule)
    return rules


def _load_snapshot(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.is_file() else None


def _video_sha256(video_name: str | None) -> str:
    """SHA-256 of the committed scenario video (video_path is repo-relative)."""
    path = REPO_ROOT / video_name if video_name else None
    if path is None or not path.is_file():
        path = SCENARIO_DIR / Path(video_name or "").name
    return sha256_hex(path.read_bytes()) if path.is_file() else sha256_hex(b"")


def _import_perception(
    session: Session, settings: Settings, eval_rows: list[dict], snapshot: dict | None, report: DemoReport,
) -> None:
    snap_tracks: dict[tuple[str, str], list[dict]] = {}
    for t in (snapshot or {}).get("tracks", []):
        snap_tracks.setdefault((t["scenario"], _norm_category(t["category"])), []).append(t)

    for row in eval_rows:
        if row.get("observed_count") is None:  # failed eval line: nothing to import
            continue
        scenario, category = row["scenario"], row["category"]
        delivery = session.query(Delivery).filter_by(scenario_id=scenario).one_or_none()
        po = session.query(PurchaseOrder).filter_by(scenario_id=scenario).one_or_none()
        line = None
        if po is not None:
            line = next((ln for ln in po.lines if _norm_category(ln.category) == _norm_category(category)), None)
        if delivery is None or line is None:
            report.perception_missing_lines.append(f"{scenario}/{category}")
            continue
        if session.query(PerceptionResult).filter_by(po_line_id=line.id).first() is not None:
            report.perception_skipped_existing += 1
            continue

        phrase = row["noun_phrase"]
        run = SamRun(
            delivery_id=delivery.id, job_id=None, video_sha256=_video_sha256(delivery.video_path),
            video_file_id=None, seg_model=settings.seg_model or "imported:eval_counts.json",
            prompt=phrase[:80], category=line.category, proxy_fps=settings.sam_proxy_fps,
            status=IMPORTED_STATUS, raw_cache_path=None, distinct_track_count=row["observed_count"],
        )
        session.add(run)
        session.flush()
        session.add(PerceptionResult(
            delivery_id=delivery.id, po_line_id=line.id, sam_run_id=run.id, category=line.category,
            noun_phrase=phrase, observed_count=row["observed_count"], max_visible=row["max_visible"],
            per_frame_counts=[], damaged_track_ids=list(row.get("damaged_track_ids") or []),
            evidence_quality=row["evidence_quality"], reasons=list(row.get("reasons") or []),
            footage_needed=row.get("footage_needed"),
        ))
        for t in snap_tracks.get((scenario, _norm_category(category)), []):
            session.add(Track(
                delivery_id=delivery.id, sam_run_id=run.id, object_id=str(t["object_id"]),
                prompt=phrase[:80], category=line.category, first_frame=t.get("first_frame"),
                last_frame=t.get("last_frame"), frame_count=t.get("frame_count"),
                confidence=t.get("confidence"),
            ))
            report.tracks_loaded += 1
        report.perception_rows += 1


def _load_rules(
    session: Session, settings: Settings, policy_markdown: str, snapshot: dict | None, report: DemoReport,
) -> None:
    if session.query(Rule).filter(
        Rule.status == RuleStatus.APPROVED.value, Rule.rule_id.isnot(None)
    ).first() is not None:
        report.rules_source = "already in DB"
        return
    rules: list[CompiledRule] | None = None
    if snapshot and snapshot.get("rules"):
        rules = [CompiledRule.model_validate(r) for r in snapshot["rules"]]
        report.rules_source = "data/demo/snapshot.json"
    else:
        rules = rules_from_compiler_cache(settings, policy_markdown)
        if rules:
            report.rules_source = "compiler cache (storage/cache)"
    if not rules:
        report.warnings.append(
            "NO APPROVED RULES LOADED: neither data/demo/snapshot.json nor a complete compiler cache "
            "(storage/cache) exists here, so verdicts cannot be computed. On the Mac that ran the "
            "policy compile, run scripts/export_demo_snapshot.py and commit data/demo/snapshot.json."
        )
        return
    version = (snapshot or {}).get("policy_version") or policy_version_of(policy_markdown)
    for rule in rules:
        if validate_rule(rule):  # never approve a rule that fails validation
            report.warnings.append(f"skipped invalid rule {rule.rule_id}")
            continue
        session.add(Rule(
            clause=rule.source_clause, policy_version=version, category=rule.goods_category or None,
            rule_type=f"compiled:{rule.condition.field}", action=rule.action,
            description=(f"Compiled from clause {rule.source_clause}: "
                         f"{rule.condition.field} {rule.condition.op} {rule.condition.value}"),
            rule_id=rule.rule_id, goods_category=rule.goods_category or None,
            condition_field=rule.condition.field, condition_op=rule.condition.op,
            condition_value=rule.condition.value, signoff_role=rule.signoff_role,
            source_text=rule.source_text, ambiguity=rule.ambiguity,
            status=RuleStatus.APPROVED.value, validation_errors=[], conflict_with=[],
        ))
        report.rules_loaded += 1


def load_demo(
    db_path: Path, manifest_path: Path, policy_path: Path, truth_path: Path, settings: Settings,
    *, eval_path: Path = EVAL_COUNTS_PATH, snapshot_path: Path = SNAPSHOT_PATH,
) -> DemoReport:
    seed(db_path, manifest_path, policy_path, truth_path)
    report = DemoReport()
    eval_rows = json.loads(eval_path.read_text()) if eval_path.is_file() else []
    if not eval_rows:
        report.warnings.append(f"{eval_path} missing or empty: no perception rows imported.")
    snapshot = _load_snapshot(snapshot_path)
    session = make_session_factory(make_engine(db_path))()
    try:
        _import_perception(session, settings, eval_rows, snapshot, report)
        _load_rules(session, settings, policy_path.read_text(), snapshot, report)
        session.commit()
    finally:
        session.close()
    return report


def print_report(report: DemoReport) -> None:
    print("Demo load (no model calls):")
    print(f"  perception rows imported={report.perception_rows} "
          f"(already present={report.perception_skipped_existing}, tracks={report.tracks_loaded})")
    print(f"  approved rules loaded={report.rules_loaded} (source: {report.rules_source})")
    for missing in report.perception_missing_lines:
        print(f"  WARNING no PO line for eval row {missing}")
    for warning in report.warnings:
        print(f"  WARNING {warning}")

