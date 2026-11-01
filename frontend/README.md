# FourthMatch frontend ("Dock Control")

React 18 + TypeScript (strict) + Vite + Tailwind v4 + Radix + TanStack Query/Table + Recharts + MSW.
Design rules: [DESIGN.md](DESIGN.md). Live spec sheet: `/styleguide`.

```bash
npm install
npm run dev:mock     # frontend-only demo: MSW serves every endpoint from repo data files
npm run dev          # against the FastAPI backend on :8000 (proxied /api)
npm run build:demo   # static demo build (MSW + scenario videos), e.g. for a public link
npm test             # vitest
npx playwright test  # e2e: every route at 1440 and 390 px, replay, command palette
```

Demo mode builds its data from `data/ground_truth.json`, `data/eval_counts.json` (the real SAM run)
and `data/policy/receiving_policy.md`, and copies `samples/scenarios/*.mp4` into `public/demo/`
(gitignored). Verdicts in demo mode are replayed from ground truth until the decision agent runs
live; the Eval page says so. Tool latencies show "—" until they come from the `model_calls` table.

Keys: `/` or `⌘K` command palette · `g 1-5` pages · `j / k / Enter` tables · `n` new delivery · `t` theme.
Routes: `/` pitch · `/dock` · `/cases` · `/cases/:poId` · `/policy` · `/analytics` · `/eval` · `/styleguide`.
