import {
  Cell as AriaCell,
  Column as AriaColumn,
  Row as AriaRow,
  Table as AriaTable,
  TableBody as AriaTableBody,
  TableHeader as AriaTableHeader,
  type CellProps as AriaCellProps,
  type ColumnProps as AriaColumnProps,
  type RowProps as AriaRowProps,
  type TableBodyProps as AriaTableBodyProps,
  type TableHeaderProps as AriaTableHeaderProps,
  type TableProps as AriaTableProps,
} from "react-aria-components";

import { ArrowDownIcon, ArrowUpIcon, ChevronLeftIcon, ChevronRightIcon } from "../icons";
import { Button } from "./button";

// The dense records table (dense-ui-craft): React Aria's Table renders a
// real <table> with grid keyboard navigation (arrow keys between cells),
// aria-sort on sortable headers, and row selection when asked for.
// Sorting and paging are *controlled*: screens keep them in the URL
// (sortDescriptor / offset as search params), never only in component state.

/** Loading: render placeholder <Row>s with a <Skeleton> in each <Cell>, not
 *  a skeleton block in renderEmptyState (that's one cell spanning the whole
 *  table, so the bars don't line up with the columns they stand in for).
 *
 *  Card frame with a horizontal scroller. `relative` contains any absolutely
 *  positioned descendants (sr-only text), or they'd widen the page (F2a bug). */
export function TableFrame({ children, footer }: { children: React.ReactNode; footer?: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-lg bg-surface shadow-card">
      <div className="relative overflow-x-auto">{children}</div>
      {footer && <div className="border-t border-line bg-inset px-4 py-2.5">{footer}</div>}
    </div>
  );
}

export function Table(props: Omit<AriaTableProps, "className" | "style">) {
  return (
    <AriaTable
      {...props}
      // First column pinned while the table scrolls sideways; its cells get
      // opaque backgrounds (bg-surface / bg-inset / --row-hover) to hide
      // what scrolls underneath.
      className="w-full border-collapse text-left [&_tr>*:first-child]:sticky [&_tr>*:first-child]:left-0 [&_tr>*:first-child]:z-[1]"
    />
  );
}

export function TableHeader<T extends object>(props: Omit<AriaTableHeaderProps<T>, "className" | "style">) {
  return <AriaTableHeader {...props} className="border-b border-line" />;
}

export type ColumnKind = "text" | "number";

export interface ColumnProps extends Omit<AriaColumnProps, "className" | "style" | "children"> {
  children: React.ReactNode;
  /** "number": right-aligned, matching number cells, sort arrow on the left. */
  kind?: ColumnKind;
}

export function Column({ children, kind = "text", ...props }: ColumnProps) {
  return (
    <AriaColumn
      {...props}
      className={`whitespace-nowrap bg-inset px-4 py-2.5 text-small font-medium text-ink-3 outline-none data-focus-visible:outline-2 data-focus-visible:-outline-offset-2 data-focus-visible:outline-accent ${kind === "number" ? "text-right" : "text-left"} ${props.allowsSorting ? "cursor-default transition-colors duration-150 ease-soft data-hovered:text-ink" : ""}`}
    >
      {({ allowsSorting, sortDirection }) => {
        // Always occupies space (transparent when unsorted) so headers don't
        // shift sideways as sorting changes.
        const arrow = allowsSorting && (
          <span aria-hidden="true" className={sortDirection ? "text-ink" : "text-transparent"}>
            {sortDirection === "descending" ? <ArrowDownIcon className="size-3.5" /> : <ArrowUpIcon className="size-3.5" />}
          </span>
        );
        // Block-level flex, arrow placed by DOM order: an inline-flex box
        // aligns to its first item's baseline, and when that item is the
        // SVG arrow (number columns) the label rose ~4px above its siblings.
        return (
          <span className={`flex items-center gap-1 ${kind === "number" ? "justify-end" : ""}`}>
            {kind === "number" && arrow}
            {children}
            {kind !== "number" && arrow}
          </span>
        );
      }}
    </AriaColumn>
  );
}

export function TableBody<T extends object>(props: Omit<AriaTableBodyProps<T>, "className" | "style">) {
  return <AriaTableBody {...props} />;
}

export function Row<T extends object>(props: Omit<AriaRowProps<T>, "className" | "style">) {
  return (
    <AriaRow
      {...props}
      className="group/row border-b border-line outline-none last:border-b-0 data-focus-visible:outline-2 data-focus-visible:-outline-offset-2 data-focus-visible:outline-accent"
    />
  );
}

export interface CellProps extends Omit<AriaCellProps, "className" | "style"> {
  /** "number": right-aligned mono with tabular figures, so columns line up. */
  kind?: ColumnKind;
}

export function Cell({ kind = "text", ...props }: CellProps) {
  return (
    <AriaCell
      {...props}
      className={`bg-surface px-4 py-2.5 outline-none transition-colors duration-150 ease-soft group-data-hovered/row:bg-row-hover group-data-selected/row:bg-accent-tint data-focus-visible:outline-2 data-focus-visible:-outline-offset-2 data-focus-visible:outline-accent ${kind === "number" ? "text-right font-mono" : ""}`}
    />
  );
}

/* ---------------------------------------------------------------- paging */

export interface PageInfo {
  /** 1-based index of the first row shown; 0 when there are no rows. */
  from: number;
  to: number;
  total: number;
  prevOffset: number | null;
  nextOffset: number | null;
}

/**
 * Pure paging math for the backend's limit/offset + X-Total-Count lists
 * (core/pagination.py). An offset past the end (a stale URL after rows were
 * deleted) still reports a sane range instead of "301–300 of 300".
 */
export function pageInfo(offset: number, limit: number, total: number): PageInfo {
  if (total <= 0) return { from: 0, to: 0, total: 0, prevOffset: null, nextOffset: null };
  const safeOffset = Math.min(Math.max(0, offset), Math.floor((total - 1) / limit) * limit);
  const to = Math.min(safeOffset + limit, total);
  return {
    from: safeOffset + 1,
    to,
    total,
    prevOffset: safeOffset > 0 ? Math.max(0, safeOffset - limit) : null,
    nextOffset: to < total ? safeOffset + limit : null,
  };
}

const count = new Intl.NumberFormat();

export interface PaginationProps {
  offset: number;
  limit: number;
  total: number;
  onChange: (offset: number) => void;
  /** Plural noun for the rows: "students". */
  noun?: string;
}

export function Pagination({ offset, limit, total, onChange, noun = "results" }: PaginationProps) {
  const page = pageInfo(offset, limit, total);
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-small text-ink-3" aria-live="polite">
        {page.total === 0 ? (
          `No ${noun}`
        ) : (
          <>
            Showing{" "}
            <span className="font-mono text-ink-2">
              {count.format(page.from)}–{count.format(page.to)}
            </span>{" "}
            of <span className="font-mono text-ink-2">{count.format(page.total)}</span> {noun}
          </>
        )}
      </p>
      <div className="flex gap-2">
        <Button size="sm" isDisabled={page.prevOffset === null} onPress={() => page.prevOffset !== null && onChange(page.prevOffset)}>
          <ChevronLeftIcon className="size-4" />
          Previous
        </Button>
        <Button size="sm" isDisabled={page.nextOffset === null} onPress={() => page.nextOffset !== null && onChange(page.nextOffset)}>
          Next
          <ChevronRightIcon className="size-4" />
        </Button>
      </div>
    </nav>
  );
}
