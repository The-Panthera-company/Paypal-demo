"use client";

import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type ICellRendererParams,
  type IRowNode,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { LeaderboardRow } from "@/lib/types";

ModuleRegistry.registerModules([AllCommunityModule]);

// Grid theme from the site's tokens: square corners, violet accents, Roboto.
const theme = themeQuartz.withParams({
  accentColor: "#5a3fe4",
  backgroundColor: "#ffffff",
  foregroundColor: "#1b192c",
  borderColor: "#e5e0ec",
  headerBackgroundColor: "#f3eeff",
  headerTextColor: "#1b192c",
  headerFontWeight: 600,
  oddRowBackgroundColor: "#fdf8fd",
  rowHoverColor: "#e5deff",
  fontFamily: "inherit",
  fontSize: 14,
  borderRadius: 0,
  wrapperBorderRadius: 0,
  rowHeight: 64,
  headerHeight: 48,
});

const catColour: Record<string, string> = {
  health: "var(--color-cat-health)",
  education: "var(--color-cat-education)",
  environment: "var(--color-cat-environment)",
  water: "var(--color-cat-water)",
};

const fmt = (cents: number, currency: string) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(cents / 100);

function ProjectCell({ data }: ICellRendererParams<LeaderboardRow>) {
  if (!data) return null;
  return (
    <div className="flex h-full items-center gap-3 leading-5">
      <span className="size-2.5 shrink-0" style={{ background: catColour[data.categoryId] ?? "#797680" }} aria-hidden />
      <span>
        <Link href={`/projects/${data.projectId}`} className="font-medium text-ink hover:text-brand hover:underline">
          {data.title}
        </Link>
        <span className="block text-xs capitalize text-text">{data.categoryId}</span>
      </span>
    </div>
  );
}

/** Match split into the floor (equal share) and the crowd share (quadratic), with cap/frozen badges */
function MatchCell({ data, context }: ICellRendererParams<LeaderboardRow, unknown, { maxMatch: number }>) {
  if (!data) return null;
  const total = data.floor.amount + data.crowd.amount || 1;
  const width = Math.max(4, Math.round((data.match.amount / (context.maxMatch || 1)) * 100));
  return (
    <div className="flex h-full flex-col justify-center gap-1.5 leading-5">
      <div className="flex items-center gap-2">
        <span className="tabular font-bold text-ink">{fmt(data.match.amount, data.match.currency)}</span>
        {data.capped && <span className="bg-accent px-1.5 text-[11px] font-bold uppercase tracking-wider text-ink">Capped</span>}
        {data.frozen && <span className="bg-danger px-1.5 text-[11px] font-bold uppercase tracking-wider text-white">Frozen</span>}
      </div>
      <div className="flex h-2 bg-line" style={{ width: `${width}%` }} aria-hidden>
        <span className="h-full bg-brand-line" style={{ width: `${(data.floor.amount / total) * 100}%` }} />
        <span className="h-full bg-brand" style={{ width: `${(data.crowd.amount / total) * 100}%` }} />
      </div>
    </div>
  );
}

export function LeaderboardGrid({ rows, refreshSeconds }: { rows: LeaderboardRow[]; refreshSeconds?: number }) {
  const router = useRouter();
  const grid = useRef<AgGridReact<LeaderboardRow>>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [shown, setShown] = useState(rows.length);
  // Pin the project column only where there is room for the numbers next to it
  const [wide, setWide] = useState(true);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const update = () => setWide(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  const currency = rows[0]?.match.currency ?? "USD";
  const categories = useMemo(() => [...new Set(rows.map((r) => r.categoryId))].sort(), [rows]);
  const context = useMemo(() => ({ maxMatch: Math.max(0, ...rows.map((r) => r.match.amount)) }), [rows]);

  // Re-fetch on the server every minute; getRowId keeps rows in place so changed cells flash.
  useEffect(() => {
    if (!refreshSeconds) return;
    const t = setInterval(() => router.refresh(), refreshSeconds * 1000);
    return () => clearInterval(t);
  }, [refreshSeconds, router]);

  useEffect(() => grid.current?.api?.onFilterChanged(), [category]);

  const columns = useMemo<ColDef<LeaderboardRow>[]>(
    () => [
      { field: "rank", headerName: "#", width: 64, pinned: "left", sort: "asc", cellClass: "tabular font-bold" },
      { field: "title", headerName: "Project", flex: 2, minWidth: wide ? 220 : 180, pinned: wide ? "left" : undefined, cellRenderer: ProjectCell },
      { field: "backerCount", headerName: "Backers", width: 110, type: "numericColumn", enableCellChangeFlash: true, cellClass: "tabular" },
      {
        headerName: "Raised",
        colId: "raised",
        width: 120,
        type: "numericColumn",
        valueGetter: (p) => p.data?.raised.amount,
        valueFormatter: (p) => fmt(p.value ?? 0, currency),
        enableCellChangeFlash: true,
        cellClass: "tabular",
      },
      {
        headerName: "Score",
        field: "score",
        width: 110,
        type: "numericColumn",
        valueFormatter: (p) => Math.round(p.value ?? 0).toLocaleString(),
        headerTooltip: "Quadratic score: (sum of square roots of each backer's gift)² minus the total. Many small backers beat one big one.",
        cellClass: "tabular",
      },
      {
        headerName: "Floor",
        colId: "floor",
        width: 110,
        type: "numericColumn",
        valueGetter: (p) => p.data?.floor.amount,
        valueFormatter: (p) => fmt(p.value ?? 0, currency),
        headerTooltip: "20% of the category pool, shared equally so new projects get a start",
        cellClass: "tabular",
      },
      {
        headerName: "Crowd share",
        colId: "crowd",
        width: 130,
        type: "numericColumn",
        valueGetter: (p) => p.data?.crowd.amount,
        valueFormatter: (p) => fmt(p.value ?? 0, currency),
        headerTooltip: "80% of the category pool, shared by score",
        cellClass: "tabular",
      },
      {
        headerName: "Match",
        colId: "match",
        flex: 1.5,
        minWidth: 200,
        valueGetter: (p) => p.data?.match.amount,
        cellRenderer: MatchCell,
        enableCellChangeFlash: true,
        headerTooltip: "Floor + crowd share, limited by the per-project cap",
      },
    ],
    [currency, wide],
  );

  const isExternalFilterPresent = useCallback(() => category !== "all", [category]);
  const doesExternalFilterPass = useCallback((node: IRowNode<LeaderboardRow>) => node.data?.categoryId === category, [category]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          Search projects
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="e.g. library"
            className="min-h-12 w-64 border border-line bg-white px-4"
          />
        </label>
        <div role="group" aria-label="Category" className="flex flex-wrap gap-2">
          {["all", ...categories].map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              aria-pressed={category === c}
              className={`min-h-12 border px-4 text-sm capitalize ${
                category === c ? "border-brand bg-brand text-white" : "border-line bg-white text-ink hover:border-brand"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
        <span className="tabular ml-auto text-sm text-ink" aria-live="polite">
          {shown} of {rows.length} projects
        </span>
      </div>

      <div className="w-full">
        <AgGridReact<LeaderboardRow>
          ref={grid}
          theme={theme}
          rowData={rows}
          columnDefs={columns}
          context={context}
          getRowId={(p) => p.data.projectId}
          quickFilterText={search}
          isExternalFilterPresent={isExternalFilterPresent}
          doesExternalFilterPass={doesExternalFilterPass}
          onModelUpdated={(e) => setShown(e.api.getDisplayedRowCount())}
          defaultColDef={{ sortable: true, resizable: true, suppressMovable: true }}
          domLayout="autoHeight"
          tooltipShowDelay={300}
          animateRows
          overlayNoRowsTemplate="<span>No projects match. Clear the search or pick another category.</span>"
        />
      </div>

      <p className="flex flex-wrap items-center gap-4 text-sm">
        <span className="flex items-center gap-2">
          <span className="inline-block h-2 w-6 bg-brand-line" aria-hidden /> Floor (equal share)
        </span>
        <span className="flex items-center gap-2">
          <span className="inline-block h-2 w-6 bg-brand" aria-hidden /> Crowd share (by number of backers)
        </span>
        <span>Hover a column header for how it&apos;s calculated.</span>
      </p>
    </div>
  );
}
