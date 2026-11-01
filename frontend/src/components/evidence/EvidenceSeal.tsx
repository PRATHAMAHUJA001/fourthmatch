import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Lock, ShieldCheck } from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { IS_MOCK } from "../../lib/demo";
import { formatTs } from "../../lib/format";
import type { EvidencePackRead } from "../../types/api";

/** Shown instead of a hash in the frontend-only demo build: the mock dataset has no real pack
 *  files, so it never claims a seal. */
export function DemoSealNote({ className }: { className?: string }) {
  return (
    <p className={cn("flex items-start gap-2 text-[13px] leading-snug text-fm-muted", className)} data-testid="demo-seal-note">
      <Lock size={14} className="mt-0.5 shrink-0" aria-hidden />
      <span>Demo build — evidence packs are sealed with SHA-256 and re-verified on the live server.</span>
    </p>
  );
}

/**
 * SHA-256 seal of the evidence pack. Re-hashes the stored files on the server when the case
 * opens (GET /api/evidence/{sha}/verify); never trusts the cached flag alone. Status is
 * always glyph + label, never colour alone. In the demo build no hash is shown.
 */
export function EvidenceSeal({ pack, className, demo = IS_MOCK }: { pack: EvidencePackRead; className?: string; demo?: boolean }) {
  const verify = useQuery({
    queryKey: ["evidence-verify", pack.sha256],
    queryFn: () => api.verifyEvidence(pack.sha256),
    staleTime: 0,
    retry: false,
    enabled: !demo,
  });
  if (demo) {
    return (
      <section className={cn("rounded-fm bg-fm-panel p-6 max-sm:p-5", className)} aria-label="Evidence pack">
        <h2 className="text-[19px] font-semibold tracking-[-0.022em]">Evidence pack</h2>
        <p className="mt-1 text-[13px] text-fm-muted">{pack.files.join(" · ")}</p>
        <DemoSealNote className="mt-4 rounded-[12px] bg-fm-raised px-3.5 py-3" />
      </section>
    );
  }
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
    <section className={cn("rounded-fm bg-fm-panel p-6 max-sm:p-5", state === "mismatch" && "shadow-[inset_0_0_0_2px_var(--fm-fraud-fill)]", className)} aria-label="Evidence pack">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="text-[19px] font-semibold tracking-[-0.022em]">Evidence pack</h2>
        <span
          role="status"
          data-testid="evidence-verify-status"
          className={cn("inline-flex items-center gap-1.5 text-[13px] font-semibold", state === "ok" ? "text-fm-verified" : state === "checking" ? "text-fm-muted" : "text-fm-fraud")}
        >
          <Icon size={14} className={state === "checking" ? "animate-spin motion-reduce:animate-none" : undefined} aria-hidden /> {label}
        </span>
      </div>
      <p className="mt-4 font-mono text-[15px] tracking-[-0.01em]">
        <span className="text-fm-faint">sha256 </span>
        <span className="text-fm-text" title={pack.sha256}>{pack.sha256.slice(0, 12)}</span>
      </p>
      <p className="mt-1 text-[13px] text-fm-muted">{pack.files.join(" · ")}</p>
      <div className="mt-4 flex items-center justify-between gap-3 text-[13px]">
        <span className="text-fm-faint">{verify.data && state !== "checking" ? `Checked ${formatTs(verify.data.checked_at)} IST` : ""}</span>
        <button type="button" onClick={() => void verify.refetch()} className="text-fm-accent-text hover:underline underline-offset-4">Re-verify</button>
      </div>
      {state === "error" && <p className="mt-2 text-[13px] text-fm-fraud">{verify.error instanceof Error ? verify.error.message : "Verification request failed."}</p>}
    </section>
  );
}
