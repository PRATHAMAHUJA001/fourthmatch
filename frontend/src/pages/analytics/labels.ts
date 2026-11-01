export const TYPE_LABEL: Record<string, string> = {
  grn_contradicted_by_video: "GRN contradicted by video",
  short_shipment_beyond_tolerance: "Short shipment",
  damaged_units_invoiced: "Damaged units invoiced",
  invoice_price_above_po: "Price above PO",
  invoice_qty_exceeds_po: "Invoice qty above PO",
  duplicate_invoice_number: "Duplicate invoice",
};

export const typeLabel = (t: string) => TYPE_LABEL[t] ?? t.replaceAll("_", " ");

export function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}
