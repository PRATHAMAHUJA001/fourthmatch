import { useState, type ReactNode } from "react";
import { Button } from "../components/ui/Button";
import { DataTable } from "../components/ui/DataTable";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "../components/ui/EmptyState";
import { FourMatchMini, FourMatchStrip } from "../components/ui/FourMatch";
import { SignalGlyph, type Signal } from "../components/ui/Glyph";
import { KpiStrip, KpiTile } from "../components/ui/KpiTile";
import { LiveCounter } from "../components/ui/LiveCounter";
import { Money, Qty } from "../components/ui/Money";
import { PageHeader, Panel } from "../components/ui/Panel";
import { StatusBadge } from "../components/ui/StatusBadge";
import { Stepper, type StageState } from "../components/ui/Stepper";
import { Kbd, Tag } from "../components/ui/Tag";
import { formatINRCompact } from "../lib/format";
import { useTheme } from "../lib/theme";
import { BrandMark, Wordmark } from "../components/shell/BrandMark";
import type { ColumnDef } from "@tanstack/react-table";
import type { Verdict } from "../types/api";
import { ColourTokens } from "./styleguide/Swatches";

const Row = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="grid items-center gap-x-6 gap-y-2 border-b border-fm-border py-3.5 first:pt-0 last:border-0 last:pb-0 sm:grid-cols-[168px_1fr]">
    <span className="fm-label">{label}</span>
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">{children}</div>
  </div>
);

const Cap = ({ children }: { children: ReactNode }) => <span className="font-mono text-[11.5px] text-fm-faint">{children}</span>;

const SIGNALS: { s: Signal; name: string; note: string }[] = [
  { s: "verified", name: "Verified", note: "square + check" },
  { s: "hold", name: "Hold", note: "diamond + pause" },
  { s: "partial", name: "Partial", note: "half circle" },
  { s: "review", name: "Review", note: "dashed ring + dot" },
  { s: "fraud", name: "Fraud risk", note: "triangle + bang" },
  { s: "live", name: "Live", note: "pulsing dot" },
  { s: "neutral", name: "Neutral", note: "open ring" },
];

const VERDICTS: Verdict[] = ["approve", "partial_pay", "hold", "human_review"];

interface Sample { sku: string; vendor: string; qty: number; paise: number; state: Verdict }
const SAMPLE: Sample[] = [
  { sku: "FX-1042", vendor: "Example Vendor A", qty: 14, paise: 124500000, state: "hold" },
  { sku: "FX-2210", vendor: "Example Vendor B", qty: 120, paise: 8640000, state: "approve" },
  { sku: "FX-3307", vendor: "Example Vendor C", qty: 48, paise: 2210050, state: "partial_pay" },
  { sku: "FX-4119", vendor: "Example Vendor D", qty: 9, paise: 0, state: "human_review" },
];
const SAMPLE_COLS: ColumnDef<Sample, unknown>[] = [
  { accessorKey: "sku", header: "SKU", cell: (i) => <span className="font-mono">{i.getValue<string>()}</span> },
  { accessorKey: "vendor", header: "Vendor" },
  { accessorKey: "qty", header: "Qty", meta: { align: "right" }, cell: (i) => <Qty value={i.getValue<number>()} unit="pcs" /> },
  { accessorKey: "paise", header: "Value", meta: { align: "right" }, cell: (i) => <Money paise={i.getValue<number>()} /> },
  { accessorKey: "state", header: "Verdict", cell: (i) => <StatusBadge verdict={i.getValue<Verdict>()} size="sm" /> },
];

const STEP_STATES: Record<string, StageState> = {
  uploading: "done", understanding: "done", tracking: "active", damage_check: "pending",
  reconciling: "pending", applying_policy: "pending", verdict: "pending",
};
const STEP_FAILED: Record<string, StageState> = { ...STEP_STATES, tracking: "failed", understanding: "done" };

function Section({ index, title, children, className }: { index: string; title: string; children: ReactNode; className?: string }) {
  return (
    <Panel index={index} title={title} className={className}>
      {children}
    </Panel>
  );
}

export function Styleguide() {
  const { theme, toggle } = useTheme();
  const [count, setCount] = useState(7);

  return (
    <div className="fm-rise">
      <PageHeader
        eyebrow="Design system · v2"
        title="FourthMatch design system"
        meta={<span>Light by default, dark on toggle. Elevation by fill, one blue accent, shape plus label instead of colour alone.</span>}
        actions={<Button variant="secondary" onClick={toggle}>{theme === "dark" ? "Switch to light" : "Switch to dark"}</Button>}
      />
      <p className="mb-6 flex items-center gap-2 text-[13px] text-fm-muted">
        <Tag tone="hold">Example values</Tag> Numbers and names in the samples below are illustrative fixtures, not case data.
      </p>

      <div className="grid gap-5 xl:grid-cols-2">
        <Section index="01" title="Colour tokens" className="xl:col-span-2"><ColourTokens /></Section>

        <Section index="02" title="Typography">
          <Row label="Display · .fm-title"><span className="text-[40px] font-bold leading-[1.05] tracking-[-0.03em]">Paper says 14.</span></Row>
          <Row label="Headline · .fm-headline"><span className="fm-headline">Hold payment until the dock agrees</span></Row>
          <Row label="Body · .fm-body"><span className="fm-body max-w-md">The vision count is 12 against a GRN of 14. Policy clause 4.2 applies, so the shortfall is held.</span></Row>
          <Row label="Label · .fm-label"><span className="fm-label">Amount held</span></Row>
          <Row label="Mono figures"><span className="font-mono text-[34px] tracking-[-0.04em]">₹12,45,000</span><Cap>IBM Plex Mono, tabular: IDs, quantities, rupees, hashes only</Cap></Row>
          <Row label="Scale">
            <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
              {[["104", "hero"], ["80", "display"], ["56", "title"], ["32", "headline"], ["24", "lede"], ["17", "body"], ["14", "ui"], ["12", "caption"]].map(([px, n]) => (
                <span key={px} className="flex items-baseline gap-1.5"><span className="font-semibold tracking-[-0.02em]" style={{ fontSize: Math.min(Number(px), 34) }}>{px}</span><Cap>{n}</Cap></span>
              ))}
            </div>
          </Row>
        </Section>

        <Section index="03" title="Signals">
          <Row label="Glyph shapes">
            <div className="grid w-full grid-cols-2 gap-x-6 gap-y-2.5 sm:grid-cols-3">
              {SIGNALS.map(({ s, name, note }) => (
                <div key={s} className="flex items-center gap-2.5">
                  <span className={`flex h-9 w-9 items-center justify-center rounded-full ${s === "verified" ? "bg-fm-verified-bg text-fm-verified" : s === "hold" || s === "partial" ? "bg-fm-hold-bg text-fm-hold" : s === "fraud" ? "bg-fm-fraud-bg text-fm-fraud" : s === "review" ? "bg-fm-review-bg text-fm-review" : s === "live" ? "bg-fm-info-bg text-fm-info" : "bg-fm-raised text-fm-muted"}`}>
                    <SignalGlyph signal={s} size={16} />
                  </span>
                  <span className="leading-tight"><span className="block text-[14px] font-medium">{name}</span><Cap>{note}</Cap></span>
                </div>
              ))}
            </div>
          </Row>
          {(["sm", "md", "lg"] as const).map((size) => (
            <Row key={size} label={`Badge · ${size}`}>
              {VERDICTS.map((v) => <StatusBadge key={v} verdict={v} size={size} />)}
              <StatusBadge fraud size={size} />
              <StatusBadge quality="reliable" size={size} />
              <StatusBadge quality="insufficient" size={size} />
            </Row>
          ))}
          <p className="mt-4 text-[14px] text-fm-muted">Shape + label, never colour alone. Each state keeps its meaning in greyscale, on a projector and for colour-blind viewers.</p>
        </Section>

        <Section index="04" title="Money & quantities">
          <Row label="Money · zero"><Money paise={0} /><Cap>0 paise, faint</Cap></Row>
          <Row label="Money · small"><Money paise={99900} /><Cap>99900 paise</Cap></Row>
          <Row label="Money · lakh grouping"><Money paise={124500000} /><Cap>124500000 paise → ₹12,45,000</Cap></Row>
          <Row label="Money · negative"><Money paise={-8640000} className="text-fm-fraud" /></Row>
          <Row label="Money · signed"><Money paise={2210050} sign className="text-fm-verified" /><Money paise={-2210050} sign className="text-fm-fraud" /></Row>
          <Row label="Qty"><Qty value={14} unit="pcs" /><Qty value={1250} unit="kg" /><Qty value={120000} unit="m" /><Qty value={null} /></Row>
          <Row label="Axis compact">
            {[99900, 1250000, 124500000, 4900000000].map((p) => <span key={p} className="font-mono text-[12px] tabular-nums">{formatINRCompact(p)}</span>)}
            <Cap>chart axes only</Cap>
          </Row>
        </Section>

        <Section index="05" title="Buttons">
          {(["sm", "md", "lg", "xl"] as const).map((size) => (
            <Row key={size} label={`Pill · ${size}`}>
              {(["accent", "primary", "secondary", "ghost", "link"] as const).map((v) => <Button key={v} variant={v} size={size}>{v}</Button>)}
            </Row>
          ))}
          <Row label="Signal pills">
            {(["hold", "verified", "danger"] as const).map((v) => <Button key={v} variant={v} size="md">{v}</Button>)}
          </Row>
          <Row label="Icon · disabled">
            <Button size="icon" variant="secondary" aria-label="Brand"><BrandMark size={14} /></Button>
            <Button variant="accent" disabled>Disabled</Button>
          </Row>
        </Section>

        <Section index="06" title="Tags & keys">
          <Row label="Tag tones">
            {(["neutral", "hold", "verified", "fraud", "review", "info", "solid"] as const).map((t) => <Tag key={t} tone={t}>{t}</Tag>)}
          </Row>
          <Row label="Identifiers"><Tag>muse-spark-1.3</Tag><Tag>sam-3.1</Tag><Tag tone="hold">clause 4.2</Tag><Tag>PO-EX-0142</Tag></Row>
          <Row label="Kbd"><span className="flex items-center gap-1"><Kbd>j</Kbd><Kbd>k</Kbd></span><span className="flex items-center gap-1"><Kbd>⌘</Kbd><Kbd>K</Kbd></span><Kbd>Enter</Kbd><Kbd>Esc</Kbd></Row>
          <Row label="Brand"><BrandMark size={22} /><Wordmark /></Row>
        </Section>

        <Section index="07" title="LiveCounter">
          <Row label="Odometer"><LiveCounter value={count} digits={2} className="text-[56px] tracking-[-0.04em] text-fm-hold" label="Boxes counted" /><Button variant="hold" onClick={() => setCount((c) => (c >= 99 ? 0 : c + 1))}>Count one more</Button></Row>
          <p className="mt-4 text-[14px] text-fm-muted">Each digit rolls on its own. Used for the vision cell while tracks accumulate, so a judge can watch the count settle on a number.</p>
        </Section>

        <Section index="08" title="KPI strip" className="xl:col-span-2">
          <KpiStrip className="md:grid-cols-4">
            <KpiTile label="Held today" tone="hold" value="₹18,60,500" hint="3 deliveries" spark={[2, 4, 3, 6, 5, 9, 8]} />
            <KpiTile label="Verified" tone="verified" value="9" unit="/ 12" delta="+2 vs yesterday" />
            <KpiTile label="Discrepancy rate" tone="fraud" value="25.0" unit="%" hint="example fixture" />
            <KpiTile label="Time to verdict" value="41" unit="s" hint="median" />
          </KpiStrip>
        </Section>

        <Section index="09" title="Four-Match" className="xl:col-span-2">
          <div className="grid gap-5">
            <div>
              <div className="fm-label mb-3">Mismatch · vision disagrees</div>
              <FourMatchStrip values={{ po: 14, grn: 14, invoice: 14, vision: 12 }} unit="box" variancePct={-14.3} />
            </div>
            <div>
              <div className="fm-label mb-3">Match · all four agree</div>
              <FourMatchStrip values={{ po: 12, grn: 12, invoice: 12, vision: 12 }} unit="box" />
            </div>
            <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
              <span className="fm-label">Mini</span>
              <span className="flex items-center gap-2"><FourMatchMini values={{ po: 14, grn: 14, invoice: 14, vision: 12 }} /><Cap>mismatch</Cap></span>
              <span className="flex items-center gap-2"><FourMatchMini values={{ po: 12, grn: 12, invoice: 12, vision: 12 }} /><Cap>match</Cap></span>
              <span className="flex items-center gap-2"><FourMatchMini values={{ po: 14, grn: 14, invoice: 16, vision: null }} /><Cap>no video</Cap></span>
            </div>
          </div>
        </Section>

        <Section index="10" title="Stepper">
          <div className="grid gap-5 sm:grid-cols-2">
            <div><div className="fm-label mb-2">Vertical · running</div><Stepper states={STEP_STATES} timing={{ uploading: 1200, understanding: 8400 }} /></div>
            <div><div className="fm-label mb-2">Vertical · failed</div><Stepper states={STEP_FAILED} timing={{ uploading: 900 }} /></div>
          </div>
          <div className="mt-6 border-t border-fm-border pt-5">
            <div className="fm-label mb-2">Horizontal</div>
            <Stepper orientation="horizontal" states={STEP_STATES} />
          </div>
        </Section>

        <Section index="11" title="DataTable">
          <p className="mb-3 text-[14px] text-fm-muted">Sortable headers, mono right-aligned numbers, keyboard navigation off here (one table per page may own j / k).</p>
          <div className="-mx-5 -mb-5 border-t border-fm-border">
            <DataTable<Sample> columns={SAMPLE_COLS} data={SAMPLE} label="Sample table" />
          </div>
        </Section>

        <Section index="12" title="Empty, error, skeleton" className="xl:col-span-2">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-fm-sm bg-fm-raised"><EmptyState title="No deliveries yet" description="Upload dock video against a purchase order to start." /></div>
            <div className="rounded-fm-sm bg-fm-raised"><ErrorState message="The decision service did not answer in time." action={<Button size="sm">Retry</Button>} /></div>
            <div className="flex flex-col gap-3 rounded-fm-sm bg-fm-raised p-5">
              <Skeleton className="h-5 w-1/2" />
              <SkeletonRows rows={3} />
            </div>
          </div>
        </Section>
      </div>
    </div>
  );
}
