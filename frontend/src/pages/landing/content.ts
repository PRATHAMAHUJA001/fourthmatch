/** Pure helpers for the landing story. Unit-tested in tests/landing.test.ts. */
import type { CitedRule } from "../../types/api";

export { SCENARIO_FRAMES } from "../../lib/media";

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
