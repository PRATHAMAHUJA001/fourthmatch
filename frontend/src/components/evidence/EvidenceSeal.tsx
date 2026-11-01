import { useMutation } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { formatTs } from "../../lib/format";
import type { EvidencePackRead } from "../../types/api";

/** SHA-256 seal of the evidence pack, re-verifiable on demand. */
export function EvidenceSeal({ pack, className }: { pack: EvidencePackRead; className?: string }) {
  const verify = useMutation({ mutationFn: () => api.verifyEvidence(pack.sha256) });
  const ok = verify.data?.verified ?? pack.verified;
  return (
    <div className={cn("flex flex-col gap-2 rounded-fm border border-fm-border bg-fm-raised p-3", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="fm-label">Evidence pack</span>
        <span className={cn("inline-flex items-center gap-1 font-cond text-[10.5px] font-semibold uppercase tracking-[0.08em]", ok ? "text-fm-verified" : "text-fm-fraud")}>
          <ShieldCheck size={12} /> {verify.isPending ? "Re-hashing…" : ok ? "Verified untouched" : "Hash mismatch"}
        </span>
      </div>
      <div className="font-mono text-[11px] leading-snug text-fm-muted break-all">
        <span className="text-fm-faint">sha256 </span>
        <span className="text-fm-text">{pack.sha256.slice(0, 16)}</span>
        {pack.sha256.slice(16, 40)}…
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[10.5px] text-fm-faint">{pack.files.join(" · ")}</span>
        <button type="button" onClick={() => verify.mutate()} className="font-mono text-[10.5px] text-fm-muted underline decoration-fm-border-strong underline-offset-2 hover:text-fm-text">
          re-verify
        </button>
      </div>
      {verify.data && <div className="font-mono text-[10px] text-fm-faint">checked {formatTs(verify.data.checked_at)} IST</div>}
    </div>
  );
}
