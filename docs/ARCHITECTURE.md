# FourthMatch — Architecture

Status: STEP 1 (design only). Implementation is STEP 2, after approval.
Ground truth for scenarios lives only in `samples/scenarios/manifest.json`.
All model request/response shapes are copied from `docs/MODEL_NOTES.md` — never guessed.
All numbers (counts, variance, rupees) are computed in Python. The LLM never does arithmetic.
Counts come only from SAM 3.1 tracks. Weak evidence → `human_review`, never `approve`.

---

## 1. Folder layout — `backend/app/`

```
backend/app/
  api/                      # HTTP layer only. No business logic, no SQL, no model calls.
    routers/                # one module per resource (purchase_orders.py, jobs.py, ...)
    schemas/                # request/response Pydantic models for the wire
    deps.py                 # FastAPI dependencies: session, services, config, request_id
  services/                 # use cases / orchestration. Depends on domain + Protocols only.
    perception.py           # video -> SamRun + tracks + PerceptionResult
    reconciliation.py       # PO vs GRN vs invoice vs tracks (pure numbers, via domain)
    decision.py             # rule evaluation -> Decision (approve|hold_payment|human_review)
    policy.py               # policy text -> compiled Rules (via model client Protocol)
  domain/                   # pure Python. Imports nothing from infra, fastapi, or sqlalchemy.
    schemas/                # Pydantic models crossing layers (Job, JobEvent, SamRun,
                            #   PerceptionResult, ModelConfig, ...)
    enums.py                # JobStatus, EvidenceQuality, Verdict, SamRunStatus, ...
    money.py                # format_inr (Indian grouping) — exists
    counting.py             # track merging, distinct counts, max_visible (pure, tested)
    variance.py             # quantity/price variance (pure, tested)
    rules.py                # rule evaluation (pure, tested)
    protocols.py            # Protocols: repositories, model clients, storage, cache
  infra/                    # implementations of domain Protocols. Injected via api/deps.py.
    db/
      models/               # SQLAlchemy 2.0 ORM models ONLY live here
      session.py            # engine + session factory + get_session dependency
      repositories/         # one repo per aggregate, implements domain Protocols
    meta/
      client.py             # one shared OpenAI client (Responses API), call_model()
      sam.py                # SAM 3.1 wrapper (official meta-sam-parser only)
      voice.py              # POST /v1/asr/transcribe (httpx, never via Spark)
    storage.py              # local file store (videos, evidence packs)
    cache.py                # SHA-256 keyed cache under storage/cache/
  core/                     # cross-cutting, framework-agnostic setup
    config.py               # pydantic-settings; ALL model IDs/base URL/key from .env
    logging.py              # structured JSON logging, request_id on every line
    errors.py               # AppError hierarchy (see §5)
  main.py                   # app factory: create_all on startup, routers, middleware
```

### Dependency direction (enforced)

```
api  ->  services  ->  domain  <-  infra   (infra implements domain Protocols)
core is imported by all layers for config/logging/errors only.
domain imports NOTHING from infra, fastapi, or sqlalchemy.
```

Enforcement (STEP 2 tests, `backend/tests/test_architecture.py`):
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
`damage_flags`, `perception_results`. `tracks` gains `sam_run_id`.

| Table | Columns (PK **bold**, FK →) | Notes |
|---|---|---|
| `vendors` | **id**, code UQ, name, gstin UQ, city, state, primary_category, contact_name, contact_email, payment_terms_days=30, synthetic | |
| `purchase_orders` | **id**, po_number UQ, vendor_id FK→vendors, order_date, expected_date, status=open, currency=INR, total_paise (Python, from lines), scenario_id UQ?, synthetic | |
| `po_lines` | **id**, po_id FK→purchase_orders, line_no, category, sku, description, unit, qty_ordered, unit_price_paise, tolerance_pct (from policy), line_total_paise (Python) | |
| `grns` | **id**, grn_number UQ, po_id FK→purchase_orders, received_date, storekeeper_name, signed, status=accepted, notes?, synthetic | |
| `grn_lines` | **id**, grn_id FK→grns, po_line_id FK→po_lines, qty_received, qty_damaged=0 | |
| `invoices` | **id**, invoice_number (idx, **not** unique — a seeded duplicate must be representable), po_id FK→purchase_orders, vendor_id FK→vendors, invoice_date, due_date, total_paise (Python), gst_paise=0, status=pending, synthetic | |
| `invoice_lines` | **id**, invoice_id FK→invoices, po_line_id FK→po_lines, qty_invoiced, unit_price_paise, line_total_paise | |
| `deliveries` | **id**, po_id FK→purchase_orders, grn_id FK→grns?, scenario_id UQ?, video_path?, video_file_id? (Files API), delivered_at?, vehicle_no?, driver_name?, status=recorded | |
| `jobs` | **id** (str, uuid), kind (`perception\|decision\|evidence`), status (see §3), delivery_id FK→deliveries?, po_id FK→purchase_orders?, progress_pct=0 (0–100, Python only), current_step?, error_code?, error_message?, payload JSON={}, result JSON={} (internal only), created_at, started_at?, finished_at? | one row per pipeline run |
| `job_events` | **id**, job_id FK→jobs (cascade, idx), seq, event_type, message, payload JSON={}, created_at; `UniqueConstraint(job_id, seq)` | append-only; seq assigned in Python (`max+1` in the txn). SSE streams **only** these stored rows |
| `model_calls` | **id**, purpose, model, latency_ms?, input_tokens?, output_tokens?, total_tokens?, cache_hit=false, status (`ok\|error\|fallback`), error?, request_meta JSON={}, created_at | one row per model call (see §6) |
| `sam_runs` | **id**, delivery_id FK→deliveries (idx), job_id FK→jobs?, video_sha256 (64, idx), video_file_id?, seg_model (copied from config at run time — audit), prompt, category, proxy_fps?, status (`queued\|running\|completed\|failed\|cached`), raw_cache_path?, distinct_track_count? (Python: unique `object_id`), error?, created_at, finished_at?; `UniqueConstraint(video_sha256, prompt, seg_model, proxy_fps)` | a SAM execution/provenance record, **separate** from its tracks; re-running parsing/merging must never re-call SAM on a cache hit |
| `tracks` | **id**, delivery_id FK→deliveries, **sam_run_id FK→sam_runs (idx)**, object_id, prompt, category, first_frame?, last_frame?, frame_count?, confidence?; `UniqueConstraint(sam_run_id, object_id)` | populated **only** by the perception pipeline from SAM output — never seeded, never from an LLM |
| `damage_flags` | **id**, track_id FK→tracks (idx), delivery_id FK→deliveries, frame_index?, reason_code, confidence?, source (`sam\|perception\|human`), created_at | any cited `track_id`/`frame_index` is checked in Python to exist before insert |
| `perception_results` | **id**, delivery_id FK→deliveries, sam_run_id FK→sam_runs (UQ per run+category), category, prompt, track_count (Python, distinct SAM ids), max_visible (Python, max distinct ids in any single frame), evidence_quality (`strong\|weak\|none`), reasons JSON=[] (stable codes, e.g. `low_frame_coverage`), created_at | persisted form of the `PerceptionResult` domain schema; the schema is what crosses layers, this row is its record |
| `rules` | **id**, clause (idx, e.g. `4.2`), policy_version, category?, rule_type, threshold_pct?, threshold_paise?, action (`approve\|hold_payment\|human_review`), description | compiled from one numbered policy clause |
| `decisions` | **id**, po_id FK→purchase_orders, delivery_id FK→deliveries?, verdict (`approve\|hold_payment\|human_review`), reason, policy_clauses JSON=[], variance_pct? (Python), amount_at_risk_paise=0 (Python), decided_by=agent, created_at | weak/`none` evidence can only yield `human_review` |
| `evidence_packs` | **id**, po_id FK→purchase_orders, decision_id FK→decisions?, pdf_path?, json_path?, sha256?, verified=false, created_at | PDF + JSON, SHA-256, re-verifiable |

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
queued ──► uploading ──► understanding ──► tracking ──► damage_check ──► done
   │            │              │               │              │
   └────────────┴──────────────┴───────────────┴──────────────┴──► failed
```

`failed` is terminal from any state (with `error_code`/`error_message` on the job and a
final `job_events` row). `done` is terminal. No other transitions are legal; the service
that owns the job is the only writer of `jobs.status`. Every transition writes the job row
**and** a `job_events` row in the same transaction, so SSE can replay history from
`job_events` alone (`seq` order) and never invents progress.

| State (on entry) | Work done | Written to DB |
|---|---|---|
| `queued` | Job created by API/service. | `jobs` row (`status=queued, progress_pct=0`); `job_events(seq=1, event_type=queued)` |
| `uploading` | Video bytes hashed (SHA-256); cache lookup in `storage/cache/`; Files API upload **once** per hash, `file_id` reused on retries. | `jobs.current_step=uploading`; `deliveries.video_file_id`; `sam_runs` row created (`status=queued`, `video_sha256`, `seg_model` from config); `job_events(uploading, {cache_hit})`; if raw SAM output already cached: skip to `tracking`, `sam_runs.status=cached` |
| `understanding` | Spark 1.3 video understanding via Responses API (`PERCEPTION_MODEL`). Output validated against Pydantic schema; cited IDs checked in Python. | `model_calls` row (model, latency_ms, tokens, cache_hit=false); `job_events(understanding)`; qualitative output held in the `PerceptionResult` draft (persisted in `damage_check`) — **no counts taken from this call** |
| `tracking` | SAM 3.1 via `infra/meta/sam.py` (buffer stream → parse offline with official `meta_sam_parser`; see `docs/MODEL_NOTES.md` §5); tracks merged/counted in pure Python. | `sam_runs.status=running→completed`, `distinct_track_count`, `raw_cache_path`; `tracks` rows (one per distinct `object_id`); raw SAM output cached by video SHA-256; `model_calls` row for the SAM call; `job_events(tracking, {distinct_track_count})` |
| `damage_check` | Damage assessment over tracks/frames; evidence quality assessed in Python (`track_count`, `max_visible`, frame coverage → `strong\|weak\|none` + reason codes). | `damage_flags` rows; `perception_results` row (`track_count`, `max_visible`, `evidence_quality`, `reasons`); `job_events(damage_check, {evidence_quality})` |
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
  against SAM counts in Python and evaluate `rules`. `evidence_quality in {weak, none}`
  forces `human_review`.

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

**Model calls (`infra/meta/client.py`, STEP 2):**

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
  buffer-then-parse-offline, official `meta_sam_parser`); voice in `infra/meta/voice.py`
  (`POST /v1/asr/transcribe`, `VOICE_MODEL`). Request shapes copied from
  `docs/MODEL_NOTES.md` only.

---

## 7. What STEP 2 will implement (not in this step)

1. `core/config.py` (pydantic-settings — add `pydantic-settings`, `fastapi`, `uvicorn`,
   `ruff`, `mypy`, `pytest` to requirements/tooling as needed), `core/logging.py`, `core/errors.py`.
2. `infra/db/`: engine, session dependency, all ORM models in §2, `create_all` on startup (SQLite now).
3. `infra/meta/client.py` as in §6; `infra/storage.py`; `infra/cache.py` (SHA-256 keyed).
4. Endpoints: `GET /api/health`, `GET /api/purchase-orders`, `GET /api/purchase-orders/{id}`
   (404 → §5 shape).
5. `pytest`: health, list POs, 404 on a missing PO (+ architecture tests in §1).
   Configure `ruff` + `mypy`. Run, show output. Done = tests pass, ruff + mypy clean.

---

## 8. Boundary checklist (verify against this doc; enforced in STEP 2)

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

