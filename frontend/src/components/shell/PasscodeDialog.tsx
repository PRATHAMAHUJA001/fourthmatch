import * as Dialog from "@radix-ui/react-dialog";
import { KeyRound, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { registerPasscodePrompt } from "../../lib/api";
import { Button } from "../ui/Button";

/** Demo-mode gate: asks for the passcode when the API answers demo_passcode_required. Mount once. */
export function PasscodeDialog() {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const pending = useRef<Promise<string | null> | null>(null);
  const resolver = useRef<((v: string | null) => void) | null>(null);

  const ask = useCallback((why: string | null) => {
    // Concurrent requests share one prompt.
    if (pending.current) return pending.current;
    setReason(why);
    setValue("");
    setOpen(true);
    pending.current = new Promise<string | null>((resolve) => { resolver.current = resolve; });
    return pending.current;
  }, []);

  useEffect(() => {
    registerPasscodePrompt(ask);
    return () => registerPasscodePrompt(null);
  }, [ask]);

  const finish = (result: string | null) => {
    setOpen(false);
    resolver.current?.(result);
    resolver.current = null;
    pending.current = null;
  };

  return (
    <Dialog.Root open={open} onOpenChange={(o) => { if (!o) finish(null); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-black/55" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[60] w-[min(400px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-fm border border-fm-border-strong bg-fm-panel">
          <div className="flex items-center justify-between border-b border-fm-border px-4 py-3">
            <Dialog.Title className="flex items-center gap-2 text-[14px] font-semibold"><KeyRound size={14} /> Demo passcode</Dialog.Title>
            <Dialog.Close className="rounded-fm-sm p-1 text-fm-muted hover:bg-fm-raised hover:text-fm-text" aria-label="Close"><X size={15} /></Dialog.Close>
          </div>
          <form onSubmit={(e) => { e.preventDefault(); if (value.trim()) finish(value.trim()); }}>
            <div className="flex flex-col gap-2 p-4">
              <Dialog.Description className="text-[12.5px] text-fm-muted">
                This public demo only accepts changes with a passcode. Browsing the recorded cases needs none.
              </Dialog.Description>
              {reason && <p className="text-[12px] text-fm-fraud" role="alert">{reason}</p>}
              <label className="fm-label" htmlFor="demo-passcode">Passcode</label>
              <input
                id="demo-passcode"
                type="password"
                autoComplete="off"
                autoFocus
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="h-9 rounded-fm-sm border border-fm-border-strong bg-fm-sunken px-2 font-mono text-[13px] outline-none focus:border-fm-hold"
              />
            </div>
            <div className="flex justify-end gap-2 border-t border-fm-border px-4 py-3">
              <Button type="button" variant="ghost" size="sm" onClick={() => finish(null)}>Cancel</Button>
              <Button type="submit" variant="accent" size="sm" disabled={!value.trim()}>Continue</Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
