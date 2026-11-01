/** Pure helpers for the landing story. Unit-tested in tests/landing.test.ts. */
import type { CitedRule } from "../../types/api";

/** Frames extracted from the scenario videos (see DESIGN.md, media pipeline). Keyed by scenario id. */
export const SCENARIO_FRAMES: Record<string, string> = {
  scn1_clean: "/media/scn1_clean_f2.webp",
  scn2_short: "/media/scn2_short_f2.webp",
  scn3_damage: "/media/scn3_damage_f1.webp",
  scn4_mixed: "/media/scn4_mixed_f2.webp",
};

/** Verbatim clause excerpt, cut at a word boundary. Never paraphrased. */
export function excerpt(text: string, max = 190) {
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  return `${cut.slice(0, cut.lastIndexOf(" "))}…`;
}

/** The clause that says video evidence prevails, if the case cites one; else the first cited. */
export function videoClause(rules: CitedRule[]): CitedRule | undefined {
  return rules.find((r) => /video/i.test(r.source_text)) ?? rules[0];
}
