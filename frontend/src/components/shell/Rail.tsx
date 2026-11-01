import { BarChart3, FileText, FlaskConical, FolderOpen, Moon, Sun, Video } from "lucide-react";
import { NavLink } from "react-router-dom";
import { useTheme } from "../../lib/theme";
import { cn } from "../../lib/cn";

const NAV = [
  { to: "/dock", label: "Dock Live", icon: Video },
  { to: "/cases", label: "Cases", icon: FolderOpen },
  { to: "/policy", label: "Policy", icon: FileText },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/eval", label: "Eval", icon: FlaskConical },
];

export function Rail() {
  const { theme, toggle } = useTheme();
  return (
    <nav className="flex w-14 shrink-0 flex-col items-center border-r border-fm-border bg-fm-panel py-2" aria-label="Primary">
      <div className="flex flex-col items-center gap-1">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "relative flex w-11 flex-col items-center gap-0.5 rounded-fm-sm px-1 py-2 text-[9px] font-medium leading-none text-fm-muted transition-colors duration-[var(--fm-motion)] hover:text-fm-text",
                isActive && "bg-fm-raised text-fm-text",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute inset-y-2 left-0 w-[2px] rounded-full bg-fm-hold" aria-hidden />}
                <Icon size={17} strokeWidth={1.8} aria-hidden />
                <span className="text-center">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
      <div className="mt-auto flex flex-col items-center gap-1">
        <NavLink
          to="/styleguide"
          className={({ isActive }) =>
            cn("flex w-11 flex-col items-center gap-0.5 rounded-fm-sm px-1 py-2 text-[9px] font-medium text-fm-muted hover:text-fm-text", isActive && "bg-fm-raised text-fm-text")
          }
        >
          <span className="font-mono text-[13px] leading-none">Aa</span>
          <span>Guide</span>
        </NavLink>
        <button
          type="button"
          onClick={toggle}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          className="flex w-11 flex-col items-center gap-0.5 rounded-fm-sm px-1 py-2 text-[9px] font-medium text-fm-muted hover:text-fm-text"
        >
          {theme === "dark" ? <Sun size={16} aria-hidden /> : <Moon size={16} aria-hidden />}
          <span>{theme === "dark" ? "Light" : "Dark"}</span>
        </button>
      </div>
    </nav>
  );
}
