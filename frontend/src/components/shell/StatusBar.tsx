import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { IS_MOCK } from "../../lib/demo";

const MODELS = [
  { id: "muse-spark-1.3", role: "perception, decision" },
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

/** Slim footer bar: API health, the Meta models in use, policy version, IST clock. */
export function StatusBar() {
  const now = useClock();
  const health = useQuery({ queryKey: ["health"], queryFn: () => fetch("/api/health").then((r) => r.ok), refetchInterval: 30_000 });
  const policy = useQuery({ queryKey: ["policy"], queryFn: api.policy, retry: false });
  const ok = health.data === true;
  const time = now.toLocaleTimeString("en-IN", { hour12: false, timeZone: "Asia/Kolkata" });
  return (
    <footer className="border-t border-fm-border bg-fm-bg">
      <div className="mx-auto flex h-10 max-w-[1440px] items-center gap-5 overflow-hidden px-4 text-[12px] text-fm-muted sm:px-6 lg:px-8">
        <span className="flex shrink-0 items-center gap-1.5">
          <span className={cn("h-1.5 w-1.5 rounded-full", health.isLoading ? "bg-fm-faint" : ok ? "bg-fm-verified-fill" : "bg-fm-fraud-fill")} aria-hidden />
          {IS_MOCK ? "API replay" : ok ? "API ok" : health.isLoading ? "API …" : "API down"}
        </span>
        <span className="flex min-w-0 items-center gap-4 max-md:hidden">
          {MODELS.map((m) => (
            <span key={m.id} className="whitespace-nowrap" title={m.role}>
              <span className="font-mono text-fm-text">{m.id}</span> <span className="text-fm-faint">{m.role}</span>
            </span>
          ))}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-4 whitespace-nowrap">
          {policy.data && <span className="font-mono max-sm:hidden">{policy.data.document_no} v{policy.data.version}</span>}
          <span className="font-mono tabular-nums text-fm-text">{time} IST</span>
        </span>
      </div>
    </footer>
  );
}
