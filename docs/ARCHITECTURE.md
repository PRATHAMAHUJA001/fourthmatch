# FourthMatch — Architecture

Status: implemented. Sections 1-8 are the original design, refreshed where the code moved on; sections
9-15 document what was added after (decision agent, evidence, dashboard, eval, voice remark, demo gate,
SPA serving). Where this file and the code disagree, the code wins; please fix the file.
Ground truth for scenarios lives only in `samples/scenarios/manifest.json`.
All model request/response shapes are copied from `docs/MODEL_NOTES.md` — never guessed.
All numbers (counts, variance, rupees) are computed in Python. The LLM never does arithmetic.
Counts come only from SAM 3.1 tracks. Insufficient (weak) evidence → `human_review`, never `approve`.

---

## 1. Folder layout — `backend/app/`

```
backend/app/
  api/                      # HTTP layer only. No business logic, no SQL, no model calls.
    routers/                # cases, dashboard, deliveries, evidence, health, policies, purchase_orders
    deps.py                 # session, services, settings, pipeline runner, decision agent, transcriber
    deps_reporting.py       # wiring for dashboard, policy docs and evidence (session -> repo -> service)
    deps_demo.py            # demo gate: require_demo_passcode, require_live_upload (see section 14)
  services/                 # use cases / orchestration. Depends on domain + Protocols.
    perception.py           # PerceptionPipeline: stages A-E, remark, decision hand-off, job events
    decision_agent.py       # DecisionAgent: tool loop + guards + fallback
    agent_tools.py          # tool schemas + CaseToolbox (deterministic tools)
    case_facts.py           # CaseFacts snapshot for the agent
    cases.py                # CaseService: verdicts recomputed on read via domain.decision
    line_facts.py           # LineDecisionInput assembly shared by cases and simulation
    policy_compiler.py      # policy markdown -> CompiledRule (PENDING_APPROVAL), approve/reject
    policy_docs.py          # the policy document + clause view
    simulation.py           # policy what-if, calls domain.decision
    purchase_orders.py, deliveries.py
    evidence.py             # EvidenceService: build_pack, get_artifact, verify
    dashboard.py            # DashboardService: dock KPIs, analytics, eval read model
    eval_report.py          # EvalResults assembly from stored evidence (no model calls)
    eval_files.py           # load/save eval labels, manifest, expected verdicts, results
  domain/                   # pure Python. Imports nothing from infra, fastapi, or sqlalchemy.
    schemas/                # Pydantic models crossing layers (cases, perception, decision_agent,
                            #   evidence, dashboard, eval, remark, policies, simulation, ...)
    enums.py                # JobStatus, EvidenceQuality (reliable|insufficient), Verdict, ...
    money.py                # format_inr (Indian grouping)
    counting.py             # filter, merge re-entered tracks, count, evidence quality, phrase coverage
    decision.py             # decide_delivery: THE decision function
    rules.py                # FIELD_CATALOG, validate_rule, evaluate_rule
    agent_logic.py          # recompute, guards (validate_payload), fallback_payload, debit note
    evidence.py             # pack document assembly, canonical JSON, sha256_bytes, ports
    metrics.py              # confusion matrix, precision/recall, count_summary, latency, cost, trends
    remark.py               # validate_claims, check_remark
    rate_limit.py           # passcode_matches, SlidingWindowLimiter
    eval_images.py, policy_doc.py
    protocols.py            # Protocols: repositories, ModelClient, Transcriber, FileStore, CacheStore
  infra/                    # implementations of domain Protocols. Injected via api/deps*.py.
    db/
      models/               # SQLAlchemy 2.0 ORM models ONLY live here (purchasing, jobs, perception, decision)
      session.py            # engine (SQLite WAL pragmas) + session factory
      repositories/         # cases, dashboard, decisions, evaluation, evidence, policies, purchase_orders, simulation
    meta/
      client.py             # MetaModelClient: call_model, call_video_model, call_image_model,
                            #   call_tool_turn, generate_image (Responses API only)
      sam.py                # SAM 3.1 wrapper (official meta_sam_parser, buffered then parsed offline)
      asr.py                # MetaTranscriber: POST /v1/asr/transcribe over httpx (never via Spark)
    audio.py                # ffmpeg: any audio -> 16 kHz mono WAV
    video.py, frames.py     # proxy video, crops, evidence frames
    pdf.py                  # reportlab renderer (evidence pack, debit note)
    storage.py              # local file store
    cache.py                # SHA-256 keyed cache under storage/cache/
  core/                     # cross-cutting, framework-agnostic setup
    config.py               # pydantic-settings; ALL model IDs/base URL/key from .env
    logging.py              # structured JSON logging, request_id on every line
    errors.py               # AppError hierarchy (see section 5)
  seed/                     # synthetic data: manifest loader, cases, policy template, --demo snapshot
  main.py                   # app factory: create_all on startup, routers, request-id middleware, SPA mount
```

### Dependency direction (enforced)

```
api  ->  services  ->  domain  <-  infra   (infra implements domain Protocols)
core is imported by all layers for config/logging/errors only.
domain imports NOTHING from infra, fastapi, or sqlalchemy.
```

Enforcement ( `backend/tests/test_architecture.py`):
- AST import scan: `domain/` must not import `sqlalchemy`, `fastapi`, or `app.infra`.
- ORM classes (`__tablename__`) may only be defined under `infra/db/models/`.
- No model-ID literals (`muse-*`, `sam-3.1`, …) anywhere under `backend/app/` outside
  `core/config.py` defaults handling and tests; grep/AST check.
- No raw `dict` crosses a layer boundary: services/domain speak Pydantic schemas only.
- Legacy note: current `app/models.py` + `app/db.py` (pre-Step-2) are superseded by
  `infra/db/models/` + `infra/db/session.py` in STEP 2; `app/models.py` may remain only
  as a re-export shim until seed imports are migrated, then it is deleted.

### Layer rules

| Layer | May do | Must never do |
|---|---|---|
| `api/` | parse/validate wire input, map `AppError` → JSON, stream stored `job_events` over SSE | SQL, arithmetic, model calls, invent IDs |
| `services/` | orchestrate a use case, own transactions, write jobs/events | HTTP types, raw SQL, parse model JSON by hand |
| `domain/` | pure logic: counting, variance, rule eval, schemas, Protocols | I/O, env reads, imports from `infra`/`fastapi`/`sqlalchemy` |
| `infra/` | SQLAlchemy, Meta API calls, files, cache | business verdicts, arithmetic policy decisions |
| `core/` | config, logging, errors | feature logic |

---

## 2. Data model

Money is integer **paise** everywhere. Quantities are integers. `synthetic=true` on all
seeded business rows. Existing tables (`vendors`…`evidence_packs`) match
`backend/app/models.py` today; new tables are `jobs`, `job_events`, `sam_runs`,
`damage_flags`, `perception_results`. `tracks` gains `sam_run_id`. Columns not listed in a row below
(for example `perception_results.po_line_id`, `noun_phrase`, `per_frame_counts`, `damaged_track_ids`,
`footage_needed`) are in `backend/app/infra/db/models/`, which is authoritative.

| Table | Columns (PK **bold**, FK →) | Notes |
|---|---|---|
| `vendors` | **id**, code UQ, name, gstin UQ, city, state, primary_category, contact_name, contact_email, payment_terms_days=30, synthetic | |
| `purchase_orders` | **id**, po_number UQ, vendor_id FK→vendors, order_date, expected_date, status=open, currency=INR, total_paise (Python, from lines), scenario_id UQ?, synthetic | |
| `po_lines` | **id**, po_id FK→purchase_orders, line_no, category, sku, description, unit, qty_ordered, unit_price_paise, tolerance_pct (from policy), line_total_paise (Python) | |
| `grns` | **id**, grn_number UQ, po_id FK→purchase_orders, received_date, storekeeper_name, signed, status=accepted, notes?, synthetic | |
| `grn_lines` | **id**, grn_id FK→grns, po_line_id FK→po_lines, qty_received, qty_damaged=0 | |
| `invoices` | **id**, invoice_number (idx, **not** unique — a seeded duplicate must be representable), po_id FK→purchase_orders, vendor_id FK→vendors, invoice_date, due_date, total_paise (Python), gst_paise=0, status=pending, synthetic | |
| `invoice_lines` | **id**, invoice_id FK→invoices, po_line_id FK→po_lines, qty_invoiced, unit_price_paise, line_total_paise | |
| `deliveries` | **id**, po_id FK→purchase_orders, grn_id FK→grns?, scenario_id UQ?, video_path?, video_file_id? (Files API), delivered_at?, vehicle_no?, driver_name?, status=recorded, `remark_audio_path`?, `remark_transcript`?, `remark_check` JSON? | the three `remark_*` columns hold the optional voice remark (section 12); context only |
| `jobs` | **id** (str, uuid), kind (`perception\|decision\|evidence`), status (see §3), delivery_id FK→deliveries?, po_id FK→purchase_orders?, progress_pct=0 (0–100, Python only), current_step?, error_code?, error_message?, payload JSON={}, result JSON={} (internal only), created_at, started_at?, finished_at? | one row per pipeline run |
| `job_events` | **id**, job_id FK→jobs (cascade, idx), seq, event_type, message, payload JSON={}, created_at; `UniqueConstraint(job_id, seq)` | append-only; seq assigned in Python (`max+1` in the txn). SSE streams **only** these stored rows |
| `model_calls` | **id**, purpose, model, latency_ms?, input_tokens?, output_tokens?, total_tokens?, cache_hit=false, status (`ok\|error\|fallback`), error?, request_meta JSON={}, created_at | one row per model call (see §6) |
| `sam_runs` | **id**, delivery_id FK→deliveries (idx), job_id FK→jobs?, video_sha256 (64, idx), video_file_id?, seg_model (copied from config at run time — audit), prompt, category, proxy_fps?, status (`queued\|running\|completed\|failed\|cached`), raw_cache_path?, distinct_track_count? (Python: unique `object_id`), error?, created_at, finished_at?; `UniqueConstraint(video_sha256, prompt, seg_model, proxy_fps)` | a SAM execution/provenance record, **separate** from its tracks; re-running parsing/merging must never re-call SAM on a cache hit |
| `tracks` | **id**, delivery_id FK→deliveries, **sam_run_id FK→sam_runs (idx)**, object_id, prompt, category, first_frame?, last_frame?, frame_count?, confidence?; `UniqueConstraint(sam_run_id, object_id)` | populated **only** by the perception pipeline from SAM output — never seeded, never from an LLM |
| `damage_flags` | **id**, track_id FK→tracks (idx), delivery_id FK→deliveries, frame_index?, reason_code, confidence?, source (`sam\|perception\|human`), created_at | any cited `track_id`/`frame_index` is checked in Python to exist before insert |
| `perception_results` | **id**, delivery_id FK→deliveries, sam_run_id FK→sam_runs (UQ per run+category), category, prompt, track_count (Python, distinct SAM ids), max_visible (Python, max distinct ids in any single frame), evidence_quality (`reliable\|insufficient`), reasons JSON=[] (stable codes, e.g. `low_frame_coverage`), created_at | persisted form of the `PerceptionResult` domain schema; the schema is what crosses layers, this row is its record |
| `rules` | **id**, clause (idx, e.g. `4.2`), policy_version, category?, rule_type, threshold_pct?, threshold_paise?, action, description; compiled-rule columns: `rule_id` UQ?, `goods_category`?, `condition_field`/`condition_op`/`condition_value`, `tolerance_pct`?, `signoff_role`?, `source_text`?, `ambiguity`?, `status` (`pending_approval\|approved\|rejected`, default pending), `validation_errors` JSON, `conflict_with` JSON | compiled from one numbered policy clause; only `approved` rows are ever evaluated |
| `decisions` | **id**, po_id FK→purchase_orders (idx), delivery_id FK→deliveries?, verdict (`approve\|partial_pay\|hold\|human_review`), reason, policy_clauses JSON=[], variance_pct? (Python), amount_at_risk_paise=0 (Python), decided_by=agent, created_at; agent columns: `job_id`?, `source` (`agent\|fallback`), `model`?, `summary_en`?, `recommended_action`?, `amount_held_paise`=0 (Python), `trace` JSON (ordered tool steps), `lines` JSON (cited rule, clause, evidence per line), `fallback_reasons` JSON | written only by the decision agent service (section 9). Case pages do not serve these as truth: the verdict is recomputed on read and the stored row is attached with a `stale` flag |
| `evidence_packs` | **id**, po_id FK→purchase_orders (idx), decision_id FK→decisions?, delivery_id FK→deliveries? (idx), pdf_path?, json_path?, sha256? (idx, SHA-256 of the exact `evidence_pack.json` bytes), `manifest` JSON (name, path, sha256, bytes, role per file: pdf, json, debit_note, frame), verified=false, created_at | PDF + JSON, SHA-256, re-verifiable (section 10) |

Key relationships:

```
vendors 1─* purchase_orders 1─* po_lines
purchase_orders 1─* grns 1─* grn_lines ─> po_lines
purchase_orders 1─* invoices 1─* invoice_lines ─> po_lines
purchase_orders 1─* deliveries 1─* sam_runs 1─* tracks 1─* damage_flags
deliveries 1─* perception_results;  sam_runs 1─1 perception_results (per category)
jobs 1─* job_events;  jobs 1─* sam_runs;  jobs *─1 deliveries / purchase_orders
purchase_orders 1─* decisions 1─* evidence_packs;  model_calls is standalone (audit log)
```

IDs cited by any model output (`track_id`, `frame_index`, `rule_id`, `po_line_id`) are
validated in Python against the DB before use; an unknown ID rejects the whole output.

---

## 3. Job state machine

```
queued ──► uploading ──► [transcribing_remark] ──► understanding ──► tracking ──► damage_check ──► done
   │            │                    │                      │               │              │
   └────────────┴────────────────────┴──────────────────────┴───────────────┴──────────────┴──► failed
```

`transcribing_remark` runs only when the delivery has a voice remark. Its failure is an event
(`transcribing_remark_failed`), never a failed job. Tracking also emits `tracking_progress`; after `damage_check`
the pipeline emits `rendering` and `remark_checked`, then the decision agent adds `reconciling`,
`applying_policy` and `verdict` events (or `decision_failed`, which does not fail the job).

`failed` is terminal from any state (with `error_code`/`error_message` on the job and a
final `job_events` row). `done` is terminal. No other transitions are legal; the service
that owns the job is the only writer of `jobs.status`. Every transition writes the job row
**and** a `job_events` row in the same transaction, so SSE can replay history from
`job_events` alone (`seq` order) and never invents progress.

| State (on entry) | Work done | Written to DB |
|---|---|---|
| `queued` | Job created by API/service. | `jobs` row (`status=queued, progress_pct=0`); `job_events(seq=1, event_type=queued)` |
| `uploading` | Video bytes hashed (SHA-256); cache lookup in `storage/cache/`; Files API upload **once** per hash, `file_id` reused on retries. | `jobs.current_step=uploading`; `deliveries.video_file_id`; `sam_runs` row created (`status=queued`, `video_sha256`, `seg_model` from config); `job_events(uploading, {cache_hit})`; if raw SAM output already cached: skip to `tracking`, `sam_runs.status=cached` |
| `transcribing_remark` | Optional. Remark audio -> 16 kHz mono WAV (ffmpeg) -> `muse-voice-transcribe-1.0`; transcript stored on the delivery and passed to Spark as unverified context. | `deliveries.remark_transcript`; `model_calls` row (`asr_remark`); `job_events(transcribing_remark)` |
| `understanding` | Spark 1.3 video understanding via Responses API (`PERCEPTION_MODEL`). Output validated against Pydantic schema; cited IDs checked in Python. | `model_calls` row (model, latency_ms, tokens, cache_hit=false); `job_events(understanding)`; qualitative output held in the `PerceptionResult` draft (persisted in `damage_check`) — **no counts taken from this call** |
| `tracking` | SAM 3.1 via `infra/meta/sam.py` (buffer stream → parse offline with official `meta_sam_parser`; see `docs/MODEL_NOTES.md` §5); tracks merged/counted in pure Python. | `sam_runs.status=running→completed`, `distinct_track_count`, `raw_cache_path`; `tracks` rows (one per distinct `object_id`); raw SAM output cached by video SHA-256; `model_calls` row for the SAM call; `job_events(tracking, {distinct_track_count})` |
| `damage_check` | Damage assessment over tracks/frames; evidence quality assessed in Python (`observed_count`, `max_visible`, short-track and merge ratios, phrase coverage → `reliable\|insufficient` + reason codes). | `damage_flags` rows; `perception_results` row (`track_count`, `max_visible`, `evidence_quality`, `reasons`); `job_events(damage_check, {evidence_quality})` |
| `done` | Terminal. Reconciliation/decision (services, separate jobs if needed) may now read `perception_results` + `tracks`. | `jobs.status=done, progress_pct=100, finished_at`, `result` JSON (typed schema serialised); `job_events(done)` |
| `failed` | Any exception: `AppError` keeps its code; anything else becomes `internal_error` (no stack/secrets in the message). | `jobs.status=failed, error_code, error_message, finished_at`; `job_events(failed, {error_code})`; `sam_runs.status=failed` if SAM was in flight; `model_calls.status=error` if a model call failed |

Retry rules: model calls retry with jitter, **never on 4xx** (see §6). Re-entering
`tracking` for the same `video_sha256 + prompt + seg_model + proxy_fps` reuses the cached
raw SAM output and does not re-call SAM.

---

## 4. Perception boundaries (who is allowed to say what)

- **SAM 3.1 (`sam_runs`/`tracks`)** is the only source of counts.
- **Spark perception (`understanding`)** is qualitative: it may propose *reasons*, never
  numbers. Its output is Pydantic-validated; cited IDs must exist.
- **`PerceptionResult`** (domain schema, persisted as `perception_results`):
  `delivery_id, sam_run_id, category, prompt, track_count, max_visible,
  evidence_quality, reasons[]` — every numeric field computed in Python from SAM records.
- **Reconciliation/decision (services + domain)** compare PO/GRN/invoice quantities
  against SAM counts in Python and evaluate `rules`. `evidence_quality == insufficient`
  forces `human_review`.

**Decision ownership (binding):** `backend/app/domain/decision.py` is THE decision
function for the whole app — `decide_delivery(lines, rules) -> DeliveryVerdict`
(mapping: insufficient evidence / `require_signoff` → `human_review`,
`hold` → `hold`, `partial_pay` → disputed portion held; verdict vocabulary is
`approve | partial_pay | hold | human_review`). The Day-3 decision agent and the
policy simulator (`POST /api/policies/{policy_version}/simulate`) must call it and
may not compute verdicts or held amounts themselves; agents supply precomputed
`LineDecisionInput` facts (counts from SAM tracks or GRN, money in paise) only.

**Cases read model (implemented):** `GET /api/cases` and
`GET /api/cases/{po_id}` recompute verdicts on read via `decide_delivery`
from approved compiled rules — stored `Decision` rows are never trusted
as truth (same stance as the simulator's drift reporting). Full design,
contract, and file/test traceability: `docs/CASES.md`.

---

## 5. Error model

One hierarchy in `core/errors.py`. Every error crossing the API becomes:

```json
{ "error": { "code": "po_not_found", "message": "Purchase order 999 was not found.", "request_id": "req_…" } }
```

```python
class AppError(Exception):            # code, status_code, message
    code = "app_error"; status_code = 500
class NotFoundError(AppError):        # 404  e.g. po_not_found, job_not_found
class ValidationError(AppError):      # 422  schema/ID-citation failures (model_output_invalid)
class ConflictError(AppError):        # 409  illegal job transition (job_transition_invalid)
class UpstreamModelError(AppError):   # 502  Meta API failure after retries (model_upstream)
class CacheError(AppError):           # 500  cache read/write failure
```

Rules:
- `api/` registers one exception handler for `AppError` → the JSON shape above, with the
  current `request_id`. Unhandled exceptions → `500 {code: "internal_error"}` with a
  generic message; the stack goes to the log only, never to the client.
- Services raise `AppError` subclasses; they never build HTTP responses.
- Domain raises plain `ValueError`/typed domain errors; services translate them into
  `AppError` at the boundary (domain stays framework-free).
- Model-output failures (bad JSON, schema mismatch, unknown cited ID) are
  `ValidationError(code="model_output_invalid")` and also mark the job `failed`.

---

## 6. Logging & model-call accounting

**Logging (`core/logging.py`):** structured JSON, one object per line, to stdout.

```json
{"ts": "…", "level": "INFO", "logger": "app.services.perception",
 "request_id": "req_…", "job_id": "…", "message": "tracking completed", "extra": {}}
```

- `request_id` is generated per HTTP request (middleware), propagated into services,
  jobs, and model calls, and present on **every** log line (contextvar; `-` outside a
  request is forbidden — background jobs mint their own id and log it).
- No secrets, no API keys, no raw video/audio bytes, no full model prompts at INFO
  (DEBUG only, and still never the key).

**Model calls (`infra/meta/client.py`):**

- One shared `OpenAI` client: `base_url` + `api_key` + model IDs **only** from
  `core/config.py` (pydantic-settings over `.env`): `MODEL_API_KEY`, `META_BASE_URL`,
  `PERCEPTION_MODEL`, `DECISION_MODEL`, `COMPILER_MODEL`, `BULK_MODEL`, `SEG_MODEL`,
  `IMAGE_MODEL`, `VOICE_MODEL`. Never hardcoded, never read from `os.environ` elsewhere.
- `call_model(...)`: Responses API only (`client.responses.create`/`.stream`, never
  `chat.completions`); retry with jitter, **no retry on 4xx**; strict JSON parsing;
  output validated against the caller's Pydantic schema; agent loops pass
  `include=["reasoning.encrypted_content"]` and use stateless replay (per MODEL_NOTES §3).
- Every call writes one `model_calls` row **and** one structured log line with:
  `model, latency_ms, input_tokens, output_tokens, total_tokens, cache_hit`
  (`cache_hit=true` only when served from `infra/cache.py`, in which case no API call
  and no token usage occurs). Token/latency values come from the API response object —
  never estimated by an LLM.
- SAM specifics live in `infra/meta/sam.py` (Files API upload once per video SHA-256,
  buffer-then-parse-offline, official `meta_sam_parser`); voice in `infra/meta/asr.py`
  (`POST /v1/asr/transcribe`, `VOICE_MODEL`). Request shapes copied from
  `docs/MODEL_NOTES.md` only.

---

## 7. Original STEP 2 scope (done)

Config, logging and errors; the ORM models and `create_all` on startup; `MetaModelClient`, storage and
the SHA-256 cache; `GET /api/health` and the purchase-order endpoints; pytest, ruff and mypy; the
architecture tests in section 1. Everything after that is in sections 9-15.

---

## 8. Boundary checklist (verify against this doc; enforced by tests)

- [x] `domain/` imports nothing from `infra/`, FastAPI or SQLAlchemy — §1 dependency
      direction + enforcement tests (`domain/` imports nothing from `infra`, `fastapi`,
      or `sqlalchemy`; domain stays framework-free, §5).
      Enforced: `test_architecture.py::test_domain_imports_nothing_forbidden`.
- [x] `jobs` and `job_events` tables exist — §2 data model (`jobs`, `job_events` with
      `UniqueConstraint(job_id, seq)`); §3 state machine writes both in one transaction.
      Enforced: `test_new_tables_and_columns_exist`, `test_jobs_sam_perception_roundtrip`.
- [x] `sam_runs` and `tracks` are separate tables — §2: `sam_runs` is a SAM
      execution/provenance record, separate from its `tracks`; `tracks.sam_run_id`
      FK → `sam_runs` with `UniqueConstraint(sam_run_id, object_id)`.
      Enforced: `test_new_tables_and_columns_exist`.
- [x] `perception_results` has `max_visible`, `evidence_quality` and `reasons` — §2
      table definition and §4: every numeric field computed in Python from SAM records.
      Enforced: `test_new_tables_and_columns_exist`, `test_perception_result_from_fixture`.
- [x] Every model ID comes from config, none hardcoded — §1 enforcement (no model-ID
      literals under `backend/app/` outside `core/config.py`) and §6: IDs/base URL/key
      only from `core/config.py` (pydantic-settings over `.env`), injected into clients.
      Enforced: `test_no_hardcoded_model_ids_in_app`, `test_config_resolves_only_from_env`.

---

## 9. Decision agent and `MetaModelClient.call_tool_turn`

Files: `services/decision_agent.py` (loop), `services/agent_tools.py` (tool schemas, `CaseToolbox`),
`domain/agent_logic.py` (guards, recompute, fallback), `domain/schemas/decision_agent.py`
(`CaseFacts`, `RecordDecisionPayload`, `ToolTurn`, `DecisionRecord`, `DecisionRead`).

`MetaModelClient.call_tool_turn(purpose, model, instructions, input_items, tools, session, reasoning_effort="high") -> ToolTurn`
is one turn of the tool loop, using **stateless replay** (MODEL_NOTES section 3). The caller appends the
prior `output_items` and `function_call_output` items to `input_items`; the client always sends
`include=["reasoning.encrypted_content"]` and never `previous_response_id`. It returns `ToolTurn`
(`output_items`, `calls` as `ToolCall(name, arguments, call_id)`, `output_text`). Retry with jitter,
never on 4xx, and one `model_calls` row per turn, like every other call.

Flow for one delivery:

1. `build_case_facts` snapshots PO, GRN, invoice, approved rules, SAM tracks and perception results.
2. `DecisionAgent._loop` runs up to `max_agent_turns` (default 40). Tools: `get_case`,
   `compute_variance`, `get_rules`, `evaluate_rule`, `draft_debit_note`, then the terminal
   `record_decision`. Every tool is pure Python; a call that cites an unknown ID returns an error and
   does not count as coverage.
3. `agent_logic.validate_payload` checks the `record_decision` payload: `compute_variance` called for every
   line and `evaluate_rule` for every applicable (rule, line) pair; cited `po_line_id`, `rule_id`, clause,
   `track:<id>` and `frame:<n>` exist; the per-line numbers equal the tools'; the verdict matches the
   policy outcome; and `amount_held_paise` equals the Python recompute. If a line has insufficient evidence
   and the model said something else, the verdict is overridden to the recompute and noted, never approved.
4. One rejection is fed back to the model; a second, a turn-cap hit, a turn that ends without
   `record_decision`, or any `AppError` from the model client stores `agent_logic.fallback_payload`
   (straight from `domain.decision`) with `source = "fallback"` and `fallback_reasons`.
5. The `decisions` row (section 2) and `job_events` (`reconciling`, `applying_policy`, `verdict`) are
   persisted. `verdict` and the amount are `DecisionRead`; `stale` is computed on read in
   `services/cases.py` when the stored decision no longer equals the current recompute.

## 10. Evidence module

`services/evidence.py` (`EvidenceService`), `domain/evidence.py` (assembly, canonical JSON, `sha256_bytes`,
ports), `infra/pdf.py` (reportlab renderer; registers a rupee-capable font, DejaVu, else prints "Rs."),
`infra/frames.py` (evidence frames from SAM overlays or sampled video frames), `infra/db/repositories/evidence.py`.

`build_pack(delivery_id)`: decide the case live through `CaseService`; assemble the pack document in
Python; collect frames; serialise to canonical JSON; **pack hash = SHA-256 of those JSON bytes** (the PDF
footer prints it, which is why the PDF itself is not what is hashed); render the PDF and, for `partial_pay`,
a debit-note PDF; store everything; hash each file into `manifest`; re-read the stored bytes and set
`verified`. `verify(sha256)` re-hashes every manifest file and the JSON against the pack hash.

Endpoints (`api/routers/evidence.py`): `GET /api/deliveries/{id}/evidence-pack[?format=json]`,
`POST /api/deliveries/{id}/evidence-pack` (rebuild; passcode in demo mode), `GET /api/deliveries/{id}/debit-note`,
`GET /api/evidence/{sha256}/verify`. `services/cases.py` attaches the newest pack as
`CaseDetail.evidence_pack` through `latest_pack_for_po` (one SELECT).

## 11. Dashboard and eval modules

- `services/dashboard.py` + `api/routers/dashboard.py`: `GET /api/dock/kpis`, `GET /api/analytics`,
  `GET /api/eval`. Everything derives from the cases the cases service serves plus stored rows
  (`decisions`, `jobs`, `model_calls`) and committed data files. Math lives in `domain/metrics.py`
  (confusion matrix, precision/recall/F1 with undefined ratios reported as `null`, vendor risk, trend
  buckets). Wiring is in `api/deps_reporting.py`.
- `services/eval_report.py` assembles `EvalResults` (schema in `domain/schemas/eval.py`) from stored evidence
  with **no model calls**: `build_video_section` (manifest vs observed counts), `build_image_section` (only
  human-confirmed synthetic stills are scored), `build_verdict_section` (served vs agent), plus latency and
  cost via `domain/metrics.py` (`latency_entries`, `estimate_cost`, `parse_cost_rates`). Anything missing
  stays `null` and is listed in `not_measured`; no price is assumed unless `MODEL_COST_RATES` is set.
- `domain/metrics.py` also owns `count_summary`, `percentile`, `macro_average` and `verdict_score`.
  `services/eval_files.py` reads and writes labels, manifest, expected verdicts and results files.
- `scripts/run_eval.py` writes `data/eval_results.json`; `scripts/eval_counts.py` writes
  `data/eval_counts.json`; `scripts/gen_eval_images.py` and `scripts/confirm_eval_images.py` own the
  synthetic image set. `/api/eval` serves `eval_results.json`; if the database has no live `model_calls`,
  latency falls back to the measured run in that file.

## 12. Voice remark

Files: `infra/meta/asr.py` (`MetaTranscriber`), `infra/audio.py` (ffmpeg to 16 kHz mono WAV),
`domain/remark.py`, `domain/schemas/remark.py`, stage `transcribing_remark` in `services/perception.py`.

- `MetaTranscriber.transcribe` posts multipart `request` (JSON: model from `VOICE_MODEL`, `audioEncoding`
  `WAV`, mode `DIARIZATION`) and `audio` to `{META_BASE_URL}/asr/transcribe` over plain `httpx`. Retry with
  jitter on network errors and 5xx, never on 4xx; strict `Transcription` validation; cached by WAV SHA-256 +
  model; one `model_calls` row per outcome (`asr_remark`, no token counts). 32 MB cap.
- The transcript is stored on the delivery and appended to the Spark scene-understanding prompt as
  "unverified" context (a delivery without a remark keeps its original prompt and cache key).
- After counting, the remark claims are extracted with `BULK_MODEL` into `RemarkClaims`;
  `validate_claims` rejects any category that is not a PO line; `check_remark` (pure Python) marks each
  count or damage claim `supported`, `not_supported` or `unverifiable` against the observed counts and
  damage, and the delivery as `supported | not_supported | unverifiable | no_claim`. Weak evidence can neither
  support nor refute. Results go to `deliveries.remark_check` and a `remark_checked` event.
- The remark never changes a count, a damage flag or a verdict. Any failure in transcription or the check is
  an event (`transcribing_remark_failed`, `remark_check_failed`), not a failed job.

## 13. Persistence for pipeline state

`jobs` and `job_events` are the only source for progress. `GET /api/deliveries/{id}/events?job_id=&after_seq=`
(`api/routers/deliveries.py`) polls `job_events` every 0.5 s, emits SSE frames `id: seq / event: type /
data: json`, sends keep-alives, and ends after `done` or `failed`. SQLite runs in WAL mode so polling does
not block the pipeline writer. The pipeline runs one job at a time (`asyncio.Semaphore(1)`).

## 14. Demo gate

`domain/rate_limit.py`: `passcode_matches` (constant-time `hmac.compare_digest`; an empty expected passcode never
matches) and `SlidingWindowLimiter` (thread-safe deque, injectable clock, `try_acquire`,
`retry_after_seconds`). `api/deps_demo.py` applies them as FastAPI dependencies, controlled by
`DEMO_MODE`, `DEMO_PASSCODE`, `LIVE_UPLOAD_LIMIT_PER_HOUR` (default 10) in `core/config.py`:

- `require_demo_passcode` on every write or model-calling route: `POST /api/policies`,
  `POST /api/policies/{id}/simulate`, `POST /api/rules/{id}/approve|reject`, `POST /api/deliveries/{id}/decide`,
  `POST /api/deliveries/{id}/evidence-pack`. Header `X-Demo-Passcode`; 403 `demo_passcode_required`, or 403
  `live_uploads_disabled` when no server passcode is set.
- `require_live_upload` on `POST /api/deliveries`: passcode first, then the rolling-hour quota (429
  `upload_rate_limited`).
- Reads and replay of seeded cases are always open. With `DEMO_MODE` off both dependencies are no-ops.
- The limiter lives on `app.state`, so it is per process and only correct with one worker.

## 15. SPA serving

`main.py` `_mount_spa(app, settings.frontend_dist)` serves the built React app from the API process. It is
registered after every `/api` router so API routes win, and is skipped when `frontend/dist/index.html` does
not exist (API-only mode). Any GET that is not a file under `dist/` returns `index.html` so client routes such
as `/cases/3` survive a reload; unknown `/api/...` paths raise the normal JSON `endpoint_not_found`
error; a missing `assets/...` file is a 404 rather than HTML; a path outside `dist/` is never served.
The app factory also installs the request-id middleware and the `AppError` and unhandled-exception handlers
(section 5).
