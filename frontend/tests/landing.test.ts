import { describe, expect, it } from "vitest";
import { caseDetails, policy } from "../src/mocks/dataset";
import { excerpt, videoClause } from "../src/pages/landing/content";

describe("landing story helpers", () => {
  it("excerpt keeps verbatim text and cuts at a word boundary", () => {
    const text = policy.clauses.find((c) => c.clause_id === "8.4")!.text;
    const out = excerpt(text, 80);
    expect(out.endsWith("…")).toBe(true);
    expect(text.startsWith(out.slice(0, -1))).toBe(true);
    expect(excerpt("short", 80)).toBe("short");
  });
  it("videoClause picks the cited clause about video evidence", () => {
    const scn2 = caseDetails.find((c) => c.scenario_id === "scn2_short")!;
    const rule = videoClause(scn2.lines[0].cited_rules);
    expect(rule && /video/i.test(rule.source_text)).toBe(true);
    expect(scn2.clauses).toContain(rule!.source_clause);
    expect(videoClause([])).toBeUndefined();
  });
});
