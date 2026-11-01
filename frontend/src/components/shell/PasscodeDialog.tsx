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
        <Dialog.Overlay className="fm-overlay fixed inset-0 z-[60] bg-black/35 backdrop-blur-[6px]" />
        <Dialog.Content className="fm-pop fixed left-1/2 top-1/2 z-[60] w-[min(420px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-fm-xl bg-fm-panel p-8 shadow-fm-float max-sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-fm-raised text-fm-text"><KeyRound size={20} /></span>
            <Dialog.Close className="flex h-9 w-9 items-center justify-center rounded-full bg-fm-raised text-fm-muted hover:bg-fm-hover hover:text-fm-text" aria-label="Close"><X size={16} /></Dialog.Close>
          </div>
          <Dialog.Title className="mt-5 text-[24px] font-bold tracking-[-0.026em]">Demo passcode</Dialog.Title>
          <form onSubmit={(e) => { e.preventDefault(); if (value.trim()) finish(value.trim()); }}>
            <Dialog.Description className="mt-2 text-[15px] leading-snug text-fm-muted">
              This public demo only accepts changes with a passcode. Browsing the recorded cases needs none.
            </Dialog.Description>
            {reason && <p className="mt-3 text-[14px] text-fm-fraud" role="alert">{reason}</p>}
            <label className="sr-only" htmlFor="demo-passcode">Passcode</label>
            <input
              id="demo-passcode"
              type="password"
              autoComplete="off"
              autoFocus
              placeholder="Passcode"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="fm-field mt-6 h-12 w-full px-4 text-[17px]"
            />
            <div className="mt-6 flex justify-end gap-2">
              <Button type="button" variant="ghost" size="lg" onClick={() => finish(null)}>Cancel</Button>
              <Button type="submit" variant="accent" size="lg" disabled={!value.trim()}>Continue</Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
