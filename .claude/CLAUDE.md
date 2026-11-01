# FourthMatch - Meta Global AI Hackathon (built Oct 30 - Nov 4, 2026)
Agent that holds procurement payments when receiving-dock video contradicts the
PO / GRN / invoice, citing the company's own policy. All data synthetic.

**New session? Read docs/HANDOFF.md first: current status, how to run, what is next.**

## Meta Model API (base https://api.meta.ai/v1, env MODEL_API_KEY, OpenAI Python SDK)
- ALWAYS use the Responses API (client.responses.create / .stream), never chat.completions.
  Video input works only on Responses; pass include=["reasoning.encrypted_content"] in agent loops.
- PERCEPTION_MODEL=muse-spark-1.3 (video understanding via input_video)
- DECISION_MODEL=muse-spark-1.3 (reasoning effort high)
- COMPILER_MODEL=muse-spark-1.3
- BULK_MODEL=muse-spark-1.3-contributor (synthetic text, summaries; cheaper)
- SEG_MODEL=sam-3.1 (Responses API; short noun phrase + image or video; returns special-token
  text, parse it with the official SAM client library: https://dev.meta.ai/docs/sam/client-libraries
  and cookbook github.com/meta-models/meta-model-cookbook/tree/main/07_sam/01_api_basics.
  Upload a video once via the Files API and reuse its file_id.)
- VOICE: POST /v1/asr/transcribe, model muse-voice-transcribe-1.0. Never send audio to Spark 1.3.
- IMAGE_MODEL=muse-image-1.0 via /v1/images/generations: synthetic test scenes only, never evidence.
Read the relevant dev.meta.ai docs page BEFORE writing any client code. Never guess request shapes.
All model IDs come from .env, never hardcoded.

## Stack
Backend: FastAPI + Python 3.12, SQLite via SQLAlchemy (easy to swap to Postgres), background
tasks for pipelines, SSE for progress. Frontend: React 18 + TypeScript + Vite + Tailwind + Radix
+ Recharts + MSW mocks. One Dockerfile (Node build stage -> Python runtime serves API + SPA).
Backend layers: api/ -> services/ -> domain/ -> infra/ (meta clients, db, storage).

## Non-negotiables
- All numbers (counts, variance, rupees) are computed in Python. The LLM never does arithmetic.
- Counts come only from SAM tracks. Weak evidence -> human_review, never approve.
- Every model call: retry with jitter (no retry on 4xx), strict JSON parsing, log model,
  latency and tokens to a model_calls table.
- Evidence packs: PDF + JSON, SHA-256 hash, re-verifiable.
- No secrets in the repo. Run code before saying it works. One smoke test per endpoint.
- Indian number formatting for rupees (12,45,000).

## How we work (applies to every task)
- Plan first: for any task touching more than 2 files, write the plan (files, public
  functions with signatures, data shapes, tests) and STOP for my OK before coding.
- Contracts before code: every data shape crossing a layer is a Pydantic model in
  app/domain/schemas/ (ORM models live only in app/infra/db/models/). Never pass raw
  dicts across layers.
- Dependency direction: api -> services -> domain. infra implements Protocols defined in
  domain and is injected via FastAPI dependencies. domain imports nothing from infra,
  fastapi or sqlalchemy.
- Ground truth lives only in samples/scenarios/manifest.json. Never hardcode a count,
  quantity or expected verdict anywhere else.
- Pure logic (track merging, counting, variance, rule evaluation) is plain Python with
  pytest unit tests using fixture JSON in tests/fixtures/. No model calls in unit tests.
- Every model output is validated against a Pydantic schema. Any ID it cites (track_id,
  frame_index, rule_id, po_line_id) is checked in Python to exist, otherwise rejected.
- Expensive calls are cached: Files API uploads and raw SAM output keyed by the video's
  SHA-256 under storage/cache/. Re-running parsing or merging must never re-call SAM.
- Pipeline state is persisted (jobs + job_events tables). SSE only streams what is stored.
- Done means: tests pass, ruff + mypy clean, and you ran it and showed me the output.
