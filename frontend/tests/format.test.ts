import { describe, expect, it } from "vitest";
import { formatINR, formatINRCompact, formatPct, formatQty } from "../src/lib/format";

describe("formatINR — Indian grouping, paise in", () => {
  it("formats zero", () => expect(formatINR(0)).toBe("₹0"));
  it("formats sub-rupee paise", () => expect(formatINR(99900)).toBe("₹999"));
  it("uses Indian grouping 12,45,000", () => expect(formatINR(124500000)).toBe("₹12,45,000"));
  it("formats crores", () => expect(formatINR(12200000000)).toBe("₹12,20,00,000"));
  it("handles negatives with minus sign", () => expect(formatINR(-55000)).toBe("−₹550"));
});

describe("formatQty / formatPct", () => {
  it("groups quantities", () => expect(formatQty(1245000)).toBe("12,45,000"));
  it("appends unit", () => expect(formatQty(12, "box")).toBe("12 box"));
  it("signs positive pct", () => expect(formatPct(2.5)).toBe("+2.5%"));
  it("uses a true minus sign for negative pct", () => expect(formatPct(-16.66)).toBe("−16.7%"));
  it("compacts lakh and crore", () => { expect(formatINRCompact(124500000)).toBe("₹12 L"); expect(formatINRCompact(12200000000)).toBe("₹12 Cr"); });
});
