# FourthMatch frontend: design brief ("Dock Control")

Audience: hackathon judges + a CFO. It must look like real operational software
(think Bloomberg terminal x Linear x a CCTV control room), never like a template.

## Rules
- Tokens only (src/index.css). Tailwind classes: bg-fm-bg / fm-sunken / fm-panel / fm-raised / fm-hover,
  border-fm-border / fm-border-strong, text-fm-text / fm-muted / fm-faint,
  signals: fm-hold (amber, also brand accent), fm-verified, fm-fraud, fm-review, fm-info,
  each with -bg (tint) and -line (border) variants. Never hardcode hex in components.
- Fonts: font-sans (Plex Sans) for prose, font-cond (Plex Sans Condensed) for labels via the
  `fm-label` class, font-mono (Plex Mono, tabular) for EVERY number, ID, rupee, date, model name.
- Money: <Money paise={..}/> (en-IN, 12,45,000). Quantities: <Qty value unit/>. Never format by hand.
- Status: <StatusBadge verdict|quality|fraud|signal/>. Never colour alone: glyph shape + label.
- Layout: dense, 8px grid, radius <= 6px, hairline borders, no shadows, no gradients, no glass,
  no emoji, no purple, no big rounded cards. Panels use <Panel title index actions>.
- Page = <PageHeader eyebrow title meta actions/> then content. KPI rows = <KpiStrip> of <KpiTile>.
- Tables = <DataTable columns data keyboard onRowClick/>; set column meta {align:"right"} on numbers.
- Motion 150ms, functional only; respect reduced motion (global CSS handles it).
- Copy: plain, specific, no hype, sentence case. Empty states one helpful line.
- Every page: loading skeleton (<SkeletonRows/>, <Skeleton/>), error (<ErrorState/>), empty (<EmptyState/>).
- Data: TanStack Query + `api` from src/lib/api.ts. Types in src/types/api.ts. In demo mode MSW
  (src/mocks/handlers.ts, src/mocks/dataset.ts) serves everything from repo data files.
- All data is synthetic; numbers are computed in Python on the backend. Never invent numbers in UI code.

## Components (src/components/ui)
Button(variant primary|accent|secondary|ghost|hold|verified|danger, size xs|sm|md|lg|icon, asChild),
Panel, PageHeader, KpiStrip, KpiTile(label,value,unit,delta,tone,hint,spark), Spark, StatusBadge,
SignalGlyph, Money, Qty, Tag(tone), Kbd, DataTable, Stepper, FourMatchStrip, FourMatchMini,
LiveCounter, EmptyState, ErrorState, Skeleton, SkeletonRows. Brand: BrandMark, Wordmark (shell/BrandMark).
Chart colours: read CSS vars via cssVar() in src/tokens/tokens.ts.
