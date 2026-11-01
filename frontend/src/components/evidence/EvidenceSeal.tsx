import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2, ShieldCheck } from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { formatTs } from "../../lib/format";
import type { EvidencePackRead } from "../../types/api";

/**
 * SHA-256 seal of the evidence pack. Re-hashes the stored files on the server when
 * the case opens (GET /api/evidence/{sha}/verify); never trusts the cached flag alone.
 * Status is always glyph + label, never colour alone.
 */
export function EvidenceSeal({ pack, className }: { pack: EvidencePackRead; className?: string }) {
  const verify = useQuery({
    queryKey: ["evidence-verify", pack.sha256],
    queryFn: () => api.verifyEvidence(pack.sha256),
    staleTime: 0,
    retry: false,
  });
  const state: "checking" | "ok" | "mismatch" | "error" = verify.isFetching
    ? "checking"
    : verify.isError
      ? "error"
      : verify.data?.verified
        ? "ok"
        : "mismatch";
  const label = { checking: "Re-hashing…", ok: "Verified untouched", mismatch: "Hash mismatch: files changed since sealing", error: "Could not verify" }[state];
  const Icon = state === "checking" ? Loader2 : state === "ok" ? ShieldCheck : AlertTriangle;
  return (
    <div className={cn("flex flex-col gap-2 rounded-fm border bg-fm-raised p-3", state === "mismatch" ? "border-fm-fraud" : "border-fm-border", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="fm-label">Evidence pack</span>
        <span
          role="status"
          data-testid="evidence-verify-status"
          className={cn(
            "inline-flex items-center gap-1 font-cond text-[10.5px] font-semibold uppercase tracking-[0.08em]",
            state === "ok" ? "text-fm-verified" : state === "checking" ? "text-fm-muted" : "text-fm-fraud",
          )}
        >
          <Icon size={12} className={state === "checking" ? "animate-spin motion-reduce:animate-none" : undefined} /> {label}
        </span>
      </div>
      <div className="font-mono text-[11px] leading-snug text-fm-muted">
        <span className="text-fm-faint">sha256 </span>
        <span className="text-fm-text" title={pack.sha256}>{pack.sha256.slice(0, 12)}</span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[10.5px] text-fm-faint">{pack.files.join(" · ")}</span>
        <button type="button" onClick={() => void verify.refetch()} className="font-mono text-[10.5px] text-fm-muted underline decoration-fm-border-strong underline-offset-2 hover:text-fm-text">
          re-verify
        </button>
      </div>
      {verify.data && state !== "checking" && <div className="font-mono text-[10px] text-fm-faint">checked {formatTs(verify.data.checked_at)} IST</div>}
      {state === "error" && <div className="text-[11px] text-fm-fraud">{verify.error instanceof Error ? verify.error.message : "Verification request failed."}</div>}
    </div>
  );
}
