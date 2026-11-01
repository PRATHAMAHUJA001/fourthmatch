import {
  flexRender, getCoreRowModel, getSortedRowModel, useReactTable,
  type ColumnDef, type SortingState,
} from "@tanstack/react-table";
import { useEffect, useRef, useState } from "react";
import { cn } from "../../lib/cn";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> { align?: "left" | "right" | "center"; width?: string }
}

interface DataTableProps<T> {
  columns: ColumnDef<T, unknown>[];
  data: T[];
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
  /** Enables j/k/↑/↓ + Enter keyboard navigation (one table per page). */
  keyboard?: boolean;
  rowClassName?: (row: T) => string | undefined;
  initialSorting?: SortingState;
  className?: string;
  label?: string;
}

/** Sortable, keyboard-navigable table. Hairline rows, mono numbers right-aligned via column meta. */
export function DataTable<T>({ columns, data, emptyMessage = "No rows", onRowClick, keyboard, rowClassName, initialSorting = [], className, label }: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const [active, setActive] = useState(-1);
  const bodyRef = useRef<HTMLTableSectionElement>(null);
  const table = useReactTable({
    data, columns, state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const rows = table.getRowModel().rows;

  useEffect(() => {
    if (!keyboard) return;
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable || e.metaKey || e.ctrlKey) return;
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(rows.length - 1, a + 1)); }
      else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
      else if (e.key === "Enter" && active >= 0 && onRowClick && rows[active]) { onRowClick(rows[active].original); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [keyboard, rows, active, onRowClick]);

  useEffect(() => {
    if (active < 0) return;
    bodyRef.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const alignCls = (a?: string) => (a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left");

  return (
    <div className={cn("fm-scroll overflow-auto", className)}>
      <table className="w-full border-collapse text-[13.5px]" aria-label={label}>
        <thead className="sticky top-0 z-10 bg-fm-panel">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const sorted = h.column.getIsSorted();
                const sortable = h.column.getCanSort();
                const meta = h.column.columnDef.meta;
                return (
                  <th
                    key={h.id}
                    style={meta?.width ? { width: meta.width } : undefined}
                    className={cn("h-10 whitespace-nowrap border-b border-fm-border px-4 text-[12px] font-semibold tracking-[-0.003em] text-fm-muted", alignCls(meta?.align))}
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                  >
                    {sortable && !h.isPlaceholder ? (
                      <button type="button" onClick={h.column.getToggleSortingHandler()} className={cn("inline-flex items-center gap-1 hover:text-fm-text", sorted && "text-fm-text")}>
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        <span className="w-2 text-[9px]">{sorted === "asc" ? "▲" : sorted === "desc" ? "▼" : ""}</span>
                      </button>
                    ) : (
                      flexRender(h.column.columnDef.header, h.getContext())
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody ref={bodyRef}>
          {rows.length === 0 ? (
            <tr><td colSpan={columns.length} className="h-24 px-4 text-center text-fm-muted">{emptyMessage}</td></tr>
          ) : (
            rows.map((row, i) => (
              <tr
                key={row.id}
                onClick={onRowClick ? () => { setActive(i); onRowClick(row.original); } : undefined}
                onMouseEnter={keyboard ? () => setActive(i) : undefined}
                data-active={i === active || undefined}
                className={cn(
                  "group border-b border-fm-border transition-colors duration-100 last:border-0 hover:bg-fm-raised data-[active]:bg-fm-raised",
                  onRowClick && "cursor-pointer",
                  rowClassName?.(row.original),
                )}
              >
                {row.getVisibleCells().map((cell, ci) => (
                  <td key={cell.id} className={cn("relative h-[var(--fm-row-h)] whitespace-nowrap px-4 align-middle", alignCls(cell.column.columnDef.meta?.align))}>
                    {ci === 0 && <span className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-fm-accent opacity-0 group-data-[active]:opacity-100" aria-hidden />}
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
