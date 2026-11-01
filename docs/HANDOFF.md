# FourthMatch: handoff for the next session

Last updated: 2026-11-01 (end of build day 5 items; day 6 not started). Read this first, then `.claude/CLAUDE.md`
(binding rules) and the playbook (Day 5 and 6 sections) if you have it.

## Ground rules that are easy to miss
- Commits go to `main`, authored as **Pratham Ahuja <prathamahuja75@gmail.com>**, **unsigned**
  (`git config commit.gpgsign false` in cloud sessions, otherwise GitHub shows "Unverified"),
  and with **no Claude / Co-Authored-By / session lines**. No feature branches.
- CLAUDE.md "plan first": any task touching more than 2 files needs Pratham's OK on a written
  plan before coding. Subagents will (correctly) refuse a relayed OK; ask him directly.
- Numbers are computed in Python only. Never invent counts, latencies or verdicts in UI code;
  show "—" when a value is not measured yet.
- Deadline: submit by **Nov 4, 11:00 PM IST**.

## Where we are (vs the playbook)

| Day | Item | Status |
|---|---|---|
| 1 | Setup, model smoke tests, `docs/MODEL_NOTES.md` | Done |
| 2 | Seed + manifest, perception pipeline A-E, `eval_counts.py` | Done; all 5 lines PASS (`data/eval_counts.json`) |
| 3 | Policy compiler, rules approve/reject, what-if simulate | Done |
| 3 | Decision agent (muse-spark-1.3 tool loop) | **Built + unit-tested with a fake model; never run against the real API** |
| 4 | Dashboard UI (all pages, hero case screen) | Done, polished; demo mode complete |
| 5 | Evidence pack PDF+JSON, SHA-256 verify, debit note | Done, including the case page (`CaseDetail.evidence_pack` via `latest_pack_for_po`; button opens `/api/deliveries/{id}/evidence-pack`) |
| 5 | Dashboard read endpoints (kpis, analytics, eval, policy) | Done |
| 5 | Voice remark (muse-voice-transcribe-1.0) | Done: `infra/meta/asr.py`, `domain/remark.py`, `transcribing_remark` stage, remark panel + record/upload in the New delivery dialog (shown in the stepper only when the upload carried a remark; a failed transcription marks that stage failed and the pipeline continues) |
| 5 | Muse Image synthetic eval set | Scripts done (`gen_eval_images.py`, `confirm_eval_images.py`); **not run**: `data/eval_results.json` has 0 images |
| 5 | `scripts/run_eval.py` (full eval) | Done; last run has video counts and damage 5/5, everything else null (see `not_measured` in the file) |
| 5 | Deploy | Done as **AWS Lightsail files, no Docker**: `deploy/` (setup.sh, Caddy, systemd), `DEPLOY.md`, DEMO_MODE passcode + rate limit, SPA served by the API. Not deployed yet; replaces the old GCP/Dockerfile plan |
| 6 | README for judges | Done (`README.md`, with screenshots in `docs/screenshots/`). Placeholders remain for the live URL and video |
| 6 | Video, submission | Not started |

Tests at handoff: backend `pytest` 183 passed / 1 skipped, ruff + mypy clean (102 source files). Frontend
`tsc` clean, vitest 46/46, Playwright e2e 22/22 (every route at 1440 and 390 px, replay, palette, cards view).

## How to run

Backend (from `backend/`, venv `.venv`, Python 3.12):
```bash
pip install -r requirements.txt
python -m app.seed                 # REQUIRED after pulling: decisions + evidence_packs gained columns
uvicorn app.main:app --port 8000
python -m pytest -q && ruff check . && mypy app
```
Scripts (repo root `scripts/`): `smoke_models.py`, `eval_counts.py` (perception from cache, no
decision), `compile_policy_cache.py`, `run_decisions.py` (needs `MODEL_API_KEY`, exits 2 without),
`gen_eval_images.py` + `confirm_eval_images.py`, `run_eval.py` (no model calls), `export_demo_snapshot.py`,
`build_evidence_packs.py`. The order for real data is in "To do" below.

Frontend (from `frontend/`):
```bash
npm install
npm run dev:mock     # frontend-only demo: MSW serves everything from repo data files
npm run dev          # live: proxies /api to :8000
npm run build:demo   # static demo build
npx vitest run
PW_CHROMIUM_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome npx playwright test   # cloud container only
```

## Architecture notes for the parts built today
- **Decision agent**: `backend/app/services/decision_agent.py`, tools in `services/agent_tools.py`,
  guards in `domain/agent_logic.py`, schemas `domain/schemas/decision_agent.py`. Model calls go
  through `MetaModelClient.call_tool_turn` (`infra/meta/client.py`), one `model_calls` row per turn,
  `include=["reasoning.encrypted_content"]`, stateless replay. Guards reject unknown IDs, skipped
  `compute_variance`/`evaluate_rule`, and any held amount that differs from the Python recompute;
  one retry, then deterministic fallback (`source="fallback"`). Turn cap `max_agent_turns` (40).
- **Served verdicts stay the Python recompute** (`docs/CASES.md` §1). The stored agent decision is
  attached as `decision` with `source`, `fallback_reasons`, `stale` (true if policy changed since).
- **Pipeline SSE**: uploading, understanding, tracking (+ `tracking_progress`), damage_check,
  reconciling, applying_policy, verdict, done. Decision failure emits `decision_failed`, never fails the job.
- **Evidence packs**: `services/evidence.py`, `infra/pdf.py` (reportlab), `infra/frames.py`.
  Pack hash = SHA-256 of `evidence_pack.json` bytes (PDF footer shows it; hashing the PDF would be
  circular). `manifest` column hashes every file; `/api/evidence/{sha}/verify` re-hashes all.
  `GET /api/deliveries/{id}/evidence-pack[?format=json]`, `POST` rebuilds, `GET .../debit-note`.
- **Dashboard**: `services/dashboard.py`, math in `domain/metrics.py`, router `api/routers/dashboard.py`,
  wiring in `api/deps_reporting.py`.
- **Frontend**: design rules `frontend/DESIGN.md`, run notes `frontend/README.md`. Wire types in
  `frontend/src/types/api.ts` match the backend. Demo data built from `data/ground_truth.json`,
  `data/eval_counts.json`, `data/policy/receiving_policy.md` in `src/mocks/dataset.ts`.

- **Voice remark**: `infra/meta/asr.py` (httpx, `POST /v1/asr/transcribe`), `infra/audio.py` (ffmpeg to
  16 kHz WAV), pure check in `domain/remark.py`. Context only; never changes a count, flag or verdict.
- **Eval**: `services/eval_report.py` + `domain/metrics.py` build `data/eval_results.json` from stored
  evidence; null means not measured, with the reason in `not_measured`.
- **Demo gate**: `api/deps_demo.py` + `domain/rate_limit.py`; `DEMO_MODE`, `DEMO_PASSCODE`,
  `LIVE_UPLOAD_LIMIT_PER_HOUR`. Rate limiter is per process (one uvicorn worker).
- Fuller module notes: `docs/ARCHITECTURE.md` sections 9-15.

## Never run for real (needs Pratham's API key, on his Mac)
- The decision agent against muse-spark-1.3: tool-call item shapes, `encrypted_content` replay,
  strict tool schemas (`record_decision` is non-strict), whether the model cites evidence as
  `track:<id>` / `frame:<n>` (otherwise the guard rejects and it falls back). First command:
  `cd backend && python -m app.seed && python ../scripts/run_decisions.py`. If it falls back,
  read the fallback reasons and adjust prompt/guard, never the expected answers.
- The full upload -> perception -> decision pipeline end to end with a new video.

## To do, in priority order

Everything below needs Pratham's API key on his Mac (the cloud container has none). Run from the repo
root unless noted, check the output of each step before the next, and never edit expected answers to move a
score.

1. **Real-key run, in this order** (`.env` with `MODEL_API_KEY` and the model IDs):
   1. Seed: `cd backend && .venv/bin/python -m app.seed` (the seeded DB has no approved rules or
      perception rows on its own).
   2. Compile and approve the policy rules (Policy page, or `POST /api/policies` then approve each rule).
      `scripts/compile_policy_cache.py` only warms the compiler cache for the offline accuracy test.
   3. `backend/.venv/bin/python scripts/eval_counts.py` (stores perception, rewrites `data/eval_counts.json`).
   4. `backend/.venv/bin/python scripts/run_decisions.py`. First real run of the decision agent: if it falls
      back, read the fallback reasons and adjust the prompt or guard, never the expected answers.
   5. `backend/.venv/bin/python scripts/gen_eval_images.py`, look at `data/eval_images/grid.html`, count each
      picture yourself, then `scripts/confirm_eval_images.py img01=7 ...`.
   6. `backend/.venv/bin/python scripts/run_eval.py` (no model calls) -> `data/eval_results.json`. Set
      `MODEL_COST_RATES` / `MODEL_COST_CURRENCY` first only if you have real prices.
   7. `PYTHONPATH=backend backend/.venv/bin/python scripts/export_demo_snapshot.py` -> `data/demo/snapshot.json`.
   8. `PYTHONPATH=backend backend/.venv/bin/python scripts/build_evidence_packs.py`.
2. **Commit the data outputs** (`data/eval_counts.json`, `data/eval_results.json`, `data/eval_images/` labels
   and PNGs, `data/demo/snapshot.json`). Then update the README Evaluation table: replace every "pending" row
   with the number from `eval_results.json`, and remove the matching Limitations line.
3. **Run the live pipeline once end to end** with a new video and a voice remark (frontend `npm run dev` plus the
   backend) and fix any shape mismatch page by page.
4. **Deploy** per `DEPLOY.md` (Lightsail, `deploy/setup.sh`), set `MODEL_API_KEY` in `/etc/fourthmatch.env`,
   verify with the curl checks in section 4 of that file, and put the URL and passcode into the README and the
   submission notes. DEPLOY.md still says the frontend must send the passcode header; the frontend now asks for the
   passcode in a dialog and sends it on non-GET requests (`frontend/src/components/shell/PasscodeDialog.tsx`,
   `src/lib/api.ts`), so update that sentence after checking.
5. **Video and submission.** Replace `<LIVE_DEMO_URL>` and `<DEMO_VIDEO_URL>` in the README. Cut order if late:
   Muse Image set, what-if, analytics.

## Known issues / decisions already made
- Demo mode serves verdicts from ground truth, so the Eval page hides verdict accuracy there and says so.
- Mock tool latencies and "time to verdict" show "—" in demo mode by design.
- Analytics 30-day history in demo mode is synthetic and footnoted.
- `held_today_paise` sums all decided cases (no decision timestamp filter yet).
- Fixed amber block colour `#ffb224` / ink `#16171a` is intentional in both themes (`.fm-amber-block`).
- Unknown/undecidable cases count as `human_review` in the confusion matrix.
- oxlint has a few warnings (react refresh / refs), no errors.
