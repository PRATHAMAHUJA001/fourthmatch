import * as Tooltip from "@radix-ui/react-tooltip";
import { Moon, Sun, Swatch } from "./icons";
import { NavLink } from "react-router-dom";
import { cn } from "../../lib/cn";
import { useTheme } from "../../lib/theme";
import { Kbd } from "../ui/Tag";
import { NAV } from "./nav";

function RailTip({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <Tooltip.Root delayDuration={250}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content side="right" sideOffset={8} className="z-50 flex items-center gap-2 rounded-fm-sm border border-fm-border-strong bg-fm-raised px-2 py-1 text-[11.5px] text-fm-text">
          {label}
          {hint && <Kbd>{hint}</Kbd>}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export function Rail() {
  const { theme, toggle } = useTheme();
  return (
    <Tooltip.Provider>
      <nav className="flex w-[60px] shrink-0 flex-col items-center border-r border-fm-border bg-fm-panel py-2 max-sm:hidden" aria-label="Primary">
        <div className="flex w-full flex-col items-center gap-0.5">
          {NAV.map(({ to, label, short, icon: Icon, key }) => (
            <RailTip key={to} label={label} hint={`G ${key}`}>
              <NavLink
                to={to}
                aria-label={label}
                className={({ isActive }) => cn(
                  "group relative flex w-[52px] flex-col items-center gap-1 rounded-fm-sm py-2 text-fm-faint transition-colors duration-[var(--fm-motion)] hover:bg-fm-raised hover:text-fm-text",
                  isActive && "bg-fm-raised text-fm-text",
                )}
              >
                {({ isActive }) => (
                  <>
                    <span className={cn("absolute -left-[4px] inset-y-2 w-[2px] rounded-full bg-fm-hold transition-opacity", isActive ? "opacity-100" : "opacity-0")} aria-hidden />
                    <Icon size={17} strokeWidth={1.6} aria-hidden className={cn(isActive && "text-fm-hold")} />
                    <span className="font-cond text-[9.5px] font-semibold uppercase tracking-[0.06em]">{short}</span>
                  </>
                )}
              </NavLink>
            </RailTip>
          ))}
        </div>
        <div className="mt-auto flex flex-col items-center gap-0.5">
          <RailTip label="Design system">
            <NavLink to="/styleguide" aria-label="Design system" className={({ isActive }) => cn("flex h-9 w-[52px] items-center justify-center rounded-fm-sm text-fm-faint hover:bg-fm-raised hover:text-fm-text", isActive && "bg-fm-raised text-fm-text")}>
              <Swatch size={16} />
            </NavLink>
          </RailTip>
          <RailTip label={theme === "dark" ? "Switch to light" : "Switch to dark"} hint="T">
            <button type="button" onClick={toggle} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} className="flex h-9 w-[52px] items-center justify-center rounded-fm-sm text-fm-faint hover:bg-fm-raised hover:text-fm-text">
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </RailTip>
        </div>
      </nav>
    </Tooltip.Provider>
  );
}
