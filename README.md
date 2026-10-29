# FourthMatch

**Meta Global AI Hackathon · Oct 30 – Nov 4, 2026**

An agent that **holds procurement payments when receiving-dock video contradicts the
PO / GRN / invoice**, citing the company's own policy. It compares what the paperwork
*says* arrived with what the dock camera (via SAM 3.1 segmentation tracks) *actually
shows*, computes the variance in Python, and holds payment on weak or contradictory
evidence instead of approving it.

All data is synthetic. Generated images are synthetic test scenes only — never evidence.

## Status

Model layer verified end-to-end against the live Meta Model API — **7/7 smoke checks pass**
(models list, strict structured JSON, tool-calling loop, SAM image, SAM video via Files API,
ASR transcription, image generation). The FastAPI backend and React frontend are next.

## Quick start

```bash
# 1. Configure (repo root .env — never commit it)
cp .env.example .env        # then set MODEL_API_KEY

# 2. Environment (already created; recreate with:)
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt

# 3. Verify every model works with your key
backend/.venv/bin/python scripts/smoke_models.py
```

ffmpeg is required for the SAM video check (it prepares a reduced-fps proxy locally;
see `docs/MODEL_NOTES.md` for why, and the verified track counts).

## Smoke test (`scripts/smoke_models.py`)

No mocks. Prints `PASS`/`FAIL` + latency per check and exits non-zero unless all 7 pass:

| # | Check | Verified result |
|---|-------|-----------------|
| 1 | `GET /v1/models` | All required models present on the key |
| 2 | muse-spark-1.3 Responses — strict JSON schema | Parses as JSON, schema-conformant |
| 3 | muse-spark-1.3 tool loop (`compute_variance`) | Tool called, arithmetic done in Python |
| 4 | sam-3.1 image — `"cardboard box"` | 10 cartons, overlay saved |
| 5 | sam-3.1 video — Files API upload | 10 distinct tracks |
| 6 | muse-voice-transcribe-1.0 — `POST /v1/asr/transcribe` | Dock remark transcribed |
| 7 | muse-image-1.0 — dock scene generation | PNG saved |

Outputs land in `samples/out/` (`carton_overlay.png`, `gen.png`).

## Models (all IDs from `.env`, never hardcoded)

| Env var | Model | Used for |
|---------|-------|----------|
| `PERCEPTION_MODEL` / `DECISION_MODEL` / `COMPILER_MODEL` | `muse-spark-1.3` | Video understanding, decisions (reasoning: high), policy compilation — **Responses API only** |
| `BULK_MODEL` | `muse-spark-1.3-contributor` | Synthetic text, summaries |
| `SEG_MODEL` | `sam-3.1` | Segmentation/counts via the official `meta-sam-parser` — counts come only from SAM tracks |
| `VOICE_MODEL` | `muse-voice-transcribe-1.0` | Driver/dock remarks via `POST /v1/asr/transcribe` |
| `IMAGE_MODEL` | `muse-image-1.0` | Synthetic test scenes only |

Base URL: `https://api.meta.ai/v1` (OpenAI Python SDK). Exact working request/response
shapes for every model — including the gotchas (encrypted-reasoning vs `previous_response_id`,
SAM parser buffering, WEBP image payloads) — are in **[docs/MODEL_NOTES.md](docs/MODEL_NOTES.md)**.
Read it before writing any client code; don't guess shapes.

## Layout

```
backend/     FastAPI + Python 3.12 (api/ -> services/ -> domain/ -> infra/), .venv, requirements.txt
scripts/     smoke_models.py — live model verification, no mocks
docs/        MODEL_NOTES.md — verified API shapes to copy from
samples/     synthetic test media (cartoon.jpg, dock.mp4, remark.wav); outputs in samples/out/
```

Stack: FastAPI + SQLite/SQLAlchemy (Postgres-swappable), background tasks, SSE progress;
React 18 + TypeScript + Vite + Tailwind + Radix + Recharts; one Dockerfile serving API + SPA.

## Non-negotiables

- All numbers (counts, variance, rupees) are computed in Python — the LLM never does arithmetic.
- Counts come only from SAM tracks. Weak evidence → `human_review`, never approve.
- Every model call: retry with jitter (no retry on 4xx), strict JSON parsing, logged
  (model, latency, tokens) to a `model_calls` table.
- Evidence packs: PDF + JSON with SHA-256, re-verifiable.
- No secrets in the repo. Indian number formatting for rupees (12,45,000).
