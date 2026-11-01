import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { IS_MOCK } from "../../lib/demo";

const MODELS = [
  { id: "muse-spark-1.3", role: "perception · decision" },
  { id: "sam-3.1", role: "segmentation" },
  { id: "muse-voice-transcribe-1.0", role: "voice remark" },
  { id: "muse-image-1.0", role: "synthetic eval" },
];

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

/** Control-room status bar: API health, Meta models in use, policy version, IST clock. */
export function StatusBar() {
  const now = useClock();
  const health = useQuery({ queryKey: ["health"], queryFn: () => fetch("/api/health").then((r) => r.ok), refetchInterval: 30_000 });
  const policy = useQuery({ queryKey: ["policy"], queryFn: api.policy, retry: false });
  const ok = health.data === true;
  const time = now.toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" });
  return (
    <footer className="flex h-7 shrink-0 items-center gap-4 overflow-hidden border-t border-fm-border bg-fm-panel px-3 font-mono text-[10.5px] text-fm-muted">
      <span className="flex items-center gap-1.5">
        <span className={cn("h-1.5 w-1.5 rounded-full", health.isLoading ? "bg-fm-faint" : ok ? "bg-fm-verified" : "bg-fm-fraud")} aria-hidden />
        {IS_MOCK ? "API · replay" : ok ? "API · ok" : health.isLoading ? "API · …" : "API · down"}
      </span>
      <span className="h-3 w-px bg-fm-border" aria-hidden />
      <span className="flex min-w-0 items-center gap-3 max-md:hidden">
        {MODELS.map((m) => (
          <span key={m.id} className="flex items-center gap-1.5 whitespace-nowrap" title={m.role}>
            <span className="h-1 w-1 rounded-full bg-fm-verified" aria-hidden />
            {m.id}
          </span>
        ))}
      </span>
      <span className="ml-auto flex items-center gap-3 whitespace-nowrap">
        {policy.data && <span className="max-sm:hidden">{policy.data.document_no} · v{policy.data.version}</span>}
        <span className="h-3 w-px bg-fm-border max-sm:hidden" aria-hidden />
        <span className="tabular-nums text-fm-text">{time} IST</span>
      </span>
    </footer>
  );
}
