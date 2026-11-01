import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { CornerDownLeft, FileText, Moon, Play, Plus, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import { formatINR } from "../../lib/format";
import { useTheme } from "../../lib/theme";
import { StatusBadge } from "../ui/StatusBadge";
import { Kbd } from "../ui/Tag";
import { NAV } from "./nav";

const itemCls = "flex h-10 cursor-pointer items-center gap-3 rounded-[10px] px-3 text-[14px] text-fm-muted data-[selected=true]:bg-fm-raised data-[selected=true]:text-fm-text";
const groupCls = "[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-[12px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-fm-faint";

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const navigate = useNavigate();
  const { toggle } = useTheme();
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases, enabled: open });
  const policy = useQuery({ queryKey: ["policy"], queryFn: api.policy, enabled: open });
  const go = (to: string) => { onOpenChange(false); navigate(to); };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/25 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-[12vh] z-50 w-[min(640px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-fm bg-fm-panel shadow-fm-float" aria-describedby={undefined}>
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <Command label="Command palette" loop>
            <div className="flex items-center gap-3 border-b border-fm-border px-4">
              <Search size={18} strokeWidth={1.8} className="text-fm-faint" aria-hidden />
              <Command.Input autoFocus placeholder="Jump to a PO, vendor, clause or page…" className="h-14 flex-1 bg-transparent text-[17px] tracking-[-0.012em] outline-none placeholder:text-fm-faint" />
              <Kbd>esc</Kbd>
            </div>
            <Command.List className="fm-scroll max-h-[min(440px,60vh)] overflow-auto p-2">
              <Command.Empty className="px-3 py-6 text-center text-[12.5px] text-fm-muted">No match.</Command.Empty>
              <Command.Group heading="Actions" className={groupCls}>
                <Command.Item className={itemCls} onSelect={() => go("/dock?new=1")}><Plus size={14} />New delivery<span className="ml-auto font-mono text-[10.5px] text-fm-faint">upload dock video</span></Command.Item>
                <Command.Item className={itemCls} onSelect={() => go("/dock?replay=2")}><Play size={14} />Replay scn2_short pipeline<span className="ml-auto font-mono text-[10.5px] text-fm-faint">demo</span></Command.Item>
                <Command.Item className={itemCls} onSelect={() => { toggle(); onOpenChange(false); }}><Moon size={14} />Toggle theme</Command.Item>
              </Command.Group>
              <Command.Group heading="Pages" className={groupCls}>
                {NAV.map((n) => (
                  <Command.Item key={n.to} value={`${n.label} ${n.description}`} className={itemCls} onSelect={() => go(n.to)}>
                    <n.icon size={14} />{n.label}<span className="ml-auto truncate text-[11px] text-fm-faint">{n.description}</span>
                  </Command.Item>
                ))}
              </Command.Group>
              {cases.data && (
                <Command.Group heading="Cases" className={groupCls}>
                  {cases.data.map((c) => (
                    <Command.Item key={c.po_id} value={`${c.po_number} ${c.vendor_name} ${c.scenario_id ?? ""}`} className={itemCls} onSelect={() => go(`/cases/${c.po_id}`)}>
                      <span className="font-mono text-fm-text">{c.po_number}</span>
                      <span className="truncate">{c.vendor_name}</span>
                      <span className="ml-auto flex items-center gap-2">
                        {c.held_paise > 0 && <span className="font-mono text-[12px] text-fm-hold">{formatINR(c.held_paise)}</span>}
                        <StatusBadge verdict={c.verdict} size="sm" />
                      </span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
              {policy.data && (
                <Command.Group heading="Policy clauses" className={groupCls}>
                  {policy.data.clauses.map((cl) => (
                    <Command.Item key={cl.clause_id} value={`clause ${cl.clause_id} ${cl.section} ${cl.text.slice(0, 120)}`} className={itemCls} onSelect={() => go(`/policy?clause=${cl.clause_id}`)}>
                      <FileText size={14} /><span className="font-mono text-fm-text">§{cl.clause_id}</span><span className="truncate">{cl.text}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
            <div className="flex items-center gap-4 border-t border-fm-border px-4 py-2 text-[12px] text-fm-faint">
              <span className="flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> move</span>
              <span className="flex items-center gap-1"><Kbd><CornerDownLeft size={10} /></Kbd> open</span>
            </div>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
