import { BarChart3, FileText, FlaskConical, FolderOpen, Radio, type LucideIcon } from "lucide-react";

export interface NavItem { to: string; label: string; short: string; icon: LucideIcon; key: string; description: string }

export const NAV: NavItem[] = [
  { to: "/dock", label: "Dock Live", short: "Dock", icon: Radio, key: "1", description: "Receiving queue, live pipeline, today's holds" },
  { to: "/cases", label: "Cases", short: "Cases", icon: FolderOpen, key: "2", description: "Every payment decision with its evidence" },
  { to: "/policy", label: "Policy", short: "Policy", icon: FileText, key: "3", description: "Policy clauses compiled into rules, what-if replay" },
  { to: "/analytics", label: "Analytics", short: "Trends", icon: BarChart3, key: "4", description: "Rupees held, vendor risk, discrepancy mix" },
  { to: "/eval", label: "Eval", short: "Eval", icon: FlaskConical, key: "5", description: "Verdict and count accuracy vs ground truth" },
];
