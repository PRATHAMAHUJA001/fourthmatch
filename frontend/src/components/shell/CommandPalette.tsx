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

const itemCls = "flex h-11 cursor-pointer items-center gap-3 rounded-[12px] px-3 text-[14px] text-fm-text data-[selected=true]:bg-fm-raised";
const groupCls = "[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-[12px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-fm-faint";

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const navigate = useNavigate();
  const { toggle } = useTheme();
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases, enabled: open });
  const policy = useQuery({ queryKey: ["policy"], queryFn: api.policy, enabled: open });
  const go = (to: string) => { onOpenChange(false); navigate(to); };
  const shortPo = cases.data?.find((c) => c.scenario_id === "scn2_short")?.po_id;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fm-overlay fixed inset-0 z-50 bg-black/30 backdrop-blur-[6px]" />
        <Dialog.Content className="fm-pop fixed left-1/2 top-[12vh] z-50 w-[min(680px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-[22px] bg-fm-panel shadow-fm-float" aria-describedby={undefined}>
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <Command label="Command palette" loop>
            <div className="flex items-center gap-3 border-b border-fm-border px-4">
              <Search size={18} strokeWidth={1.8} className="text-fm-faint" aria-hidden />
              <Command.Input autoFocus placeholder="Jump to a PO, vendor, clause or page…" className="h-16 flex-1 bg-transparent text-[19px] tracking-[-0.012em] outline-none placeholder:text-fm-faint" />
              <Kbd>esc</Kbd>
            </div>
            <Command.List className="fm-scroll max-h-[min(440px,60vh)] overflow-auto p-2">
              <Command.Empty className="px-3 py-10 text-center text-[15px] text-fm-muted">No match.</Command.Empty>
              <Command.Group heading="Actions" className={groupCls}>
                <Command.Item className={itemCls} onSelect={() => go("/dock?new=1")}><Plus size={15} className="text-fm-muted" />New delivery<span className="ml-auto text-[12px] text-fm-faint">Upload dock video</span></Command.Item>
                {shortPo != null && <Command.Item className={itemCls} onSelect={() => go(`/dock?replay=${shortPo}`)}><Play size={15} className="text-fm-muted" />Replay the short shipment<span className="ml-auto text-[12px] text-fm-faint">Live pipeline</span></Command.Item>}
                <Command.Item className={itemCls} onSelect={() => { toggle(); onOpenChange(false); }}><Moon size={15} className="text-fm-muted" />Toggle theme</Command.Item>
              </Command.Group>
              <Command.Group heading="Pages" className={groupCls}>
                {NAV.map((n) => (
                  <Command.Item key={n.to} value={`${n.label} ${n.description}`} className={itemCls} onSelect={() => go(n.to)}>
                    <n.icon size={15} className="text-fm-muted" />{n.label}<span className="ml-auto truncate text-[12px] text-fm-faint max-sm:hidden">{n.description}</span>
                  </Command.Item>
                ))}
              </Command.Group>
              {cases.data && (
                <Command.Group heading="Cases" className={groupCls}>
                  {cases.data.map((c) => (
                    <Command.Item key={c.po_id} value={`${c.po_number} ${c.vendor_name} ${c.scenario_id ?? ""}`} className={itemCls} onSelect={() => go(`/cases/${c.po_id}`)}>
                      <span className="font-mono text-[13px]">{c.po_number}</span>
                      <span className="truncate text-fm-muted max-sm:hidden">{c.vendor_name}</span>
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
                      <FileText size={15} className="shrink-0 text-fm-muted" /><span className="shrink-0 font-semibold">§{cl.clause_id}</span><span className="truncate text-fm-muted">{cl.text}</span>
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
