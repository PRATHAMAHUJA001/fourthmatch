# FourthMatch: handoff for the next session

Last updated: 2026-11-01 (end of build day 3). Read this first, then `.claude/CLAUDE.md`
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
| 2 | Seed + manifest, perception pipeline A–E, `eval_counts.py` | Done; all 5 lines PASS (`data/eval_counts.json`) |
| 3 | Policy compiler, rules approve/reject, what-if simulate | Done |
| 3 | Decision agent (muse-spark-1.3 tool loop) | **Built + unit-tested with a fake model; never run against the real API** |
| 4 | Dashboard UI (all pages, hero case screen) | Done, polished; demo mode complete |
| 5 | Evidence pack PDF+JSON, SHA-256 verify, debit note | Done (backend). Not yet shown on the case page from the live API (see To do 1) |
| 5 | Dashboard read endpoints (kpis, analytics, eval, policy) | Done |
| 5 | Voice remark (muse-voice-transcribe-1.0) | Not started |
| 5 | Muse Image synthetic eval set | Not started |
| 5 | `scripts/run_eval.py` (full eval) | Not started |
| 5 | Deploy (Dockerfile, Cloud Run, DEMO_MODE + passcode) | Not started |
| 6 | README for judges, video, submission | Not started |

Tests at handoff: backend `pytest` 121 passed / 1 skipped, ruff + mypy clean. Frontend `tsc` clean,
vitest 27/27, Playwright e2e 22/22 (every route at 1440 and 390 px, replay, palette, cards view).

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
`build_evidence_packs.py`.

Likely order to get real data into a fresh DB (verify each step, the seeded DB has no approved
rules or perception rows on its own): seed -> compile + approve policy rules -> `eval_counts.py`
(stores perception) -> `run_decisions.py` -> `build_evidence_packs.py`.

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

## Never run for real (needs Pratham's API key, on his Mac)
- The decision agent against muse-spark-1.3: tool-call item shapes, `encrypted_content` replay,
  strict tool schemas (`record_decision` is non-strict), whether the model cites evidence as
  `track:<id>` / `frame:<n>` (otherwise the guard rejects and it falls back). First command:
  `cd backend && python -m app.seed && python ../scripts/run_decisions.py`. If it falls back,
  read the fallback reasons and adjust prompt/guard, never the expected answers.
- The full upload -> perception -> decision pipeline end to end with a new video.

## To do, in priority order
1. **Small integration**: attach `latest_pack_for_po` (evidence service) to `CaseDetail.evidence_pack`
   in `services/cases.py`; then run the frontend in live mode (`npm run dev` + backend) and fix any
   shape mismatch page by page. In live mode the case page "Evidence pack" button should open
   `/api/deliveries/{id}/evidence-pack`.
2. **First real decision run** (above), then update `docs/ARCHITECTURE.md` with the new `decisions`
   columns, `call_tool_turn`, evidence + dashboard modules (not yet documented there).
3. **Deploy** (playbook Day 5 prompt 5): multi-stage Dockerfile (Node build -> Python 3.12 slim serves
   API + SPA, non-root, port 8080), seed + load the 4 demo cases on startup, DEMO_MODE replays stored
   SSE, live uploads only with `DEMO_PASSCODE` and max 10/hour, key from env. Install a font with the
   ₹ glyph (e.g. `fonts-dejavu-core`) or PDFs print "Rs.". Alternative quick public link: `npm run build:demo`
   on any static host.
4. **Voice remark** (Day 5 prompt 2): MediaRecorder in the New delivery dialog, ffmpeg to 16 kHz wav,
   POST /v1/asr/transcribe (see MODEL_NOTES §6), transcript is context only; show "Remark not supported
   by video" when it disagrees.
5. **Muse Image eval set** (Day 5 prompt 3), then **`scripts/run_eval.py`** -> `data/eval_results.json`
   and feed the Eval page.
6. **README for judges** (Day 6 prompt 1) with eval numbers, Mermaid diagram, model table, screenshots.
7. Video (script in the playbook, Day 6). Cut order if late: voice, Muse Image, what-if, analytics.

## Known issues / decisions already made
- Demo mode serves verdicts from ground truth, so the Eval page hides verdict accuracy there and says so.
- Mock tool latencies and "time to verdict" show "—" in demo mode by design.
- Analytics 30-day history in demo mode is synthetic and footnoted.
- `held_today_paise` sums all decided cases (no decision timestamp filter yet).
- Fixed amber block colour `#ffb224` / ink `#16171a` is intentional in both themes (`.fm-amber-block`).
- Unknown/undecidable cases count as `human_review` in the confusion matrix.
- oxlint has a few warnings (react refresh / refs), no errors.
