# Cases — design, contract, and traceability

Status: implemented (Cases list + case detail, backend + MSW + UI).
This is the demo screen: PO vs GRN vs invoice vs SAM counts side-by-side,
variance, verdict badge, amount at risk, cited policy clause — one screen.

Ground truth lives only in `samples/scenarios/manifest.json`. All numbers
(counts, variance, rupees) are computed in Python; the LLM never does
arithmetic. Counts come only from SAM tracks (video) or the GRN (document
lines). Weak evidence → `human_review`, never `approve`.

Related docs: `docs/ARCHITECTURE.md` §4 (decision ownership),
`docs/EVAL.md` (accuracy story), `docs/MODEL_NOTES.md` (model shapes).

---

## 1. Decision: verdict source (recompute, never stored)

Verdicts are **recomputed on read** through `domain/decision.py`
(`decide_delivery`) from **approved compiled rules only**, using the
newest `policy_version` that has any valid approved rule.

Why not stored `Decision` rows:

- No code path in the repo writes `Decision` rows today; a stored read
  model would serve empty data.
- The policy simulator already treats stored decisions as *drift* to be
  reported, never as truth (`backend/app/services/simulation.py`).
  Cases follows the same stance so the two screens can never disagree.
- Recomputing means editing + approving a policy clause changes case
  verdicts immediately, with no stale-decision invalidation problem.

Semantics that must hold:

| Situation | Verdict served |
|---|---|
| Line `evidence_quality == "insufficient"` | `human_review`, held = full line value, at-risk = 0 |
| Any triggered `hold` rule | `hold` |
| Triggered `partial_pay` (± `require_signoff`) | `partial_pay`, held = disputed portion only |
| No perception result **and** no GRN line for every line | `verdict = null` ("Not decided") — never a fabricated approve |
| No approved compiled rules yet | Lines still evaluate (insufficient evidence still forces `human_review`); quantity/price rules simply cannot trigger until a policy is compiled + approved on the Policy page |

`held_paise` (cash withheld) and `at_risk_paise` (value genuinely at
risk) are different numbers and both are served; see the docstring in
`backend/app/domain/decision.py` for the per-verdict definitions.

## 2. HTTP contract

```
GET /api/cases           -> list[CaseSummary]
GET /api/cases/{po_id}  -> CaseDetail        (404: po_not_found, ARCHITECTURE §5 shape)
```

Authoritative shapes: `backend/app/domain/schemas/cases.py`
(mirrored by hand in `frontend/src/types/api.ts`). Money is integer
paise everywhere; dates are ISO `YYYY-MM-DD`.

- `CaseSummary` — `po_id, po_number, vendor_id, vendor_name,
  scenario_id, status, order_date, expected_date, total_paise`
  (Python sum of line totals), `verdict | null, held_paise,
  at_risk_paise, policy_version | null, lines_evaluated, lines_total`.
- `CaseDetail(CaseSummary)` — adds `delivery_id, grn_number,
  invoice_number, triggered_rule_ids, signoff_roles, lines[]`.
- `CaseLineRead` — the four-way comparison per line: `po_qty, grn_qty,
  invoiced_qty, observed_count, damage_count`, plus `evidence_source`
  (`video | document | none`), `evidence_quality`, both unit prices,
  `line_value_paise`, Python-computed `variance_pct`
  (`(po_qty − observed) / po_qty × 100`), per-line `verdict | null`,
  `held_paise, at_risk_paise, signoff_roles`, and `cited_rules[]`.
- `CitedRule` — `rule_id, source_clause, source_text, action`, resolved
  in Python from the approved rule rows. A triggered `rule_id` that does
  not resolve to an approved rule is **dropped**, never rendered
  (unknown-ID rejection, ARCHITECTURE §2).

## 3. Backend traceability

| Piece | File | Notes |
|---|---|---|
| Wire contract | `backend/app/domain/schemas/cases.py` | Pydantic only; no ORM, no I/O. Exported from `domain/schemas/__init__.py` |
| Repository Protocol | `backend/app/domain/protocols.py` → `CaseRepository` | Read-only; domain imports nothing from infra/FastAPI/SQLAlchemy |
| Read model service | `backend/app/services/cases.py` → `CaseService.list_cases() / get_case(po_id)` | Approved-rules selection, `decide_delivery`, cited-rule resolution, variance via `decision.build_facts` |
| Shared line facts | `backend/app/services/line_facts.py` → `build_line_decision_input()`, `row_to_compiled()` | Extracted verbatim from the simulator so simulation and cases assemble line facts identically; simulator now imports from here (no behaviour change) |
| SQL implementation | `backend/app/infra/db/repositories/cases.py` → `SqlCaseRepository` | SELECTs only, deliberately no write/commit; "latest row wins" ordering mirrors `SqlSimulationRepository` |
| Router | `backend/app/api/routers/cases.py` | No SQL, no verdict logic |
| Wiring | `backend/app/api/deps.py` → `get_case_service`; `backend/app/main.py` | Router mounted under `/api` |
| Decision function | `backend/app/domain/decision.py` | Unchanged; THE decision function (ARCHITECTURE §4) |

Fact precedence per line (in `line_facts.py`): latest `PerceptionResult`
wins (`evidence_source="video"`, observed = SAM count, damage =
`len(damaged_track_ids)`); else latest GRN line (`"document"`,
observed = GRN qty); else the line is unevaluable and excluded from the
decision (counted in `lines_total` but not `lines_evaluated`).

## 4. Frontend traceability

| Piece | File | Notes |
|---|---|---|
| Wire types | `frontend/src/types/api.ts` → `CaseSummary, CaseDetail, CaseLineRead, CitedRule` | Hand-mirrored from the Pydantic contract; paise everywhere |
| Fetch wrappers | `frontend/src/lib/api.ts` → `getCases(), getCase(poId)` | Surfaces the backend `error.message` on failure |
| List page | `frontend/src/pages/Cases.tsx` | KPI strip (cases, at-risk, held, needs-attention) + `DataTable`; row click → detail. KPI sums are display-only aggregation of paise fields served by Python |
| Detail page | `frontend/src/pages/CaseDetail.tsx` | Four-way line table (PO / GRN / invoiced / observed, with SAM-vs-GRN source label), evidence badge, cited-clause cards (`§clause`, rule id, action, verbatim source text), signoff roles |
| Routes | `frontend/src/App.tsx` | `/cases`, `/cases/:poId` (replaces the stub) |
| MSW mock | `frontend/src/mocks/data.ts` (`caseDetails/caseSummaries`), `frontend/src/mocks/handlers.ts` | **Mock-only synthetic fixtures** for offline dev (`npm run dev:mock`); real numbers always come from `GET /api/cases`. A judge-facing demo must run against the real backend |
| UI primitives | `components/ui/{DataTable,KpiTile,Money,Panel,StatusBadge,EmptyState}` | Reused as-is; no new design-system pieces |

Verdict vocabulary is never colour-alone: `StatusBadge` pairs icon +
label (`Verified / Partial pay / On hold / Needs review`), and
`verdict = null` renders an explicit "Not decided" text label.

## 5. Tests

| Test | File | Covers |
|---|---|---|
| `test_list_cases` | `backend/tests/test_cases.py` | Short delivery → `partial_pay`, held = at-risk = ₹1,650 (Python-checked); no-evidence PO → `verdict is None`; insufficient video → `human_review`, at-risk 0 |
| `test_get_case_detail_cites_clause` | `backend/tests/test_cases.py` | Four quantities, `variance_pct = 25.0`, `triggered_rule_ids`, cited `§4.2` with source text |
| `test_get_case_weak_evidence_line` | `backend/tests/test_cases.py` | Video line, `insufficient` → `human_review` |
| `test_missing_case_404` | `backend/tests/test_cases.py` | `po_not_found` error shape |
| Cases MSW suite | `frontend/tests/cases.test.tsx` | List badge + `₹1,650` Indian formatting; detail four-way table + `§4.2`; weak evidence shows "Needs review" + "Evidence insufficient", never "Verified" |
| Regression | `backend/tests/test_simulation.py`, `test_accuracy.py` | The `line_facts.py` extraction must not move simulator or 12-case accuracy results |

Fixtures are built as real ORM rows in a tmp SQLite DB (same pattern as
`backend/tests/test_api.py`); expected money is asserted as literal
paise computed by hand in the test comment, never copied from the
implementation's output.

## 6. Demo path

1. Seed + compile/approve the receiving policy (Policy page) so approved
   rules exist.
2. `GET /api/cases` — every PO with its live verdict.
3. Open the short-delivery case: PO 12 / GRN 9 / invoiced 12 / SAM 9,
   `partial_pay`, ₹ at risk, `§4.2` cited with verbatim clause text.
4. Open the weak-video case: `human_review`, full amount held, ₹0 at
   risk — the "weak evidence is never a basis to approve" story.
