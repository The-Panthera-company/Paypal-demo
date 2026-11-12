"use client";

import { Banner, Confirm, notify as toast } from "@/components/Status";
import { plainReport } from "@/components/AgentReport";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type ICellRendererParams,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo, useState, useTransition } from "react";
import {
  resolveCaseAction, confirmAndRemoveAction,
  reviewMilestoneAction,
  verifyAction,
  type ActionResult,
} from "@/app/admin/actions";
import type {
  AdminCase,
  AdminMilestone,
  AdminProject,
  AuditEntry,
} from "@/lib/admin";

ModuleRegistry.registerModules([AllCommunityModule]);

const theme = themeQuartz.withParams({
  accentColor: "#007190",
  borderColor: "#d9e8df",
  headerBackgroundColor: "#eef6f1",
  headerFontWeight: 600,
  oddRowBackgroundColor: "#f9faf8",
  rowHoverColor: "#d7ece6",
  fontFamily: "inherit",
  fontSize: 14,
  borderRadius: 0,
  wrapperBorderRadius: 0,
  rowHeight: 56,
});

const fmt = (cents: number, currency: string) =>
  new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(cents / 100);
const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
const words = (s: string) => s.replace(/_/g, " ");

/** Buttons that call a server action. Destructive choices ask first (heuristics H3, H5). */
type Ctx = { notify: (r: ActionResult) => void };

function Actions({
  buttons,
  notify,
}: {
  buttons: {
    label: string;
    tone: "primary" | "plain" | "danger";
    confirm?: string;
    run: () => Promise<ActionResult>;
  }[];
  notify: Ctx["notify"];
}) {
  const [pending, start] = useTransition();
  const [result, setResult] = useState<ActionResult | null>(null);
  const [asking, setAsking] = useState<(typeof buttons)[number] | null>(null);
  const run = (b: (typeof buttons)[number]) =>
    start(async () => {
      const r = await b.run();
      setResult(r);
      notify(r);
      toast(r.message, r.ok ? "success" : "error");
    });
  return (
    <div className="flex h-full items-center gap-2 leading-5">
      {buttons.map((b) => (
        <button
          key={b.label}
          type="button"
          disabled={pending}
          onClick={() => {
            if (b.confirm) setAsking(b);
            else run(b);
          }}
          className={`min-h-9 px-3 text-xs font-bold uppercase tracking-wider disabled:opacity-50 ${
            b.tone === "primary"
              ? "bg-primary text-white hover:bg-ink"
              : b.tone === "danger"
                ? "bg-danger text-white"
                : "border border-line bg-white text-ink hover:border-brand"
          }`}
        >
          {pending ? "…" : b.label}
        </button>
      ))}
      <Confirm
        open={asking !== null}
        title={asking ? `${asking.label}?` : ""}
        body={asking?.confirm}
        confirmLabel={asking?.label}
        danger={asking?.tone === "danger"}
        onCancel={() => setAsking(null)}
        onConfirm={() => {
          if (asking) run(asking);
          setAsking(null);
        }}
      />
      {result && !result.ok && (
        <span role="alert" className="text-xs font-medium text-danger">
          {result.message}
        </span>
      )}
    </div>
  );
}

function Grid<T>({
  rows,
  columns,
  empty,
  rowHeight,
}: {
  rows: T[];
  columns: ColDef<T>[];
  empty: string;
  rowHeight?: number;
}) {
  // The row usually disappears after a decision (the page reloads from the API), so the result is shown here.
  const [notice, setNotice] = useState<ActionResult | null>(null);
  const context = useMemo<Ctx>(() => ({ notify: setNotice }), []);
  return (
    <div className="space-y-3">
      {notice && (
        <Banner tone={notice.ok ? "success" : "error"}>{notice.message}</Banner>
      )}
      <AgGridReact<T>
        context={context}
        theme={theme}
        rowData={rows}
        columnDefs={columns}
        defaultColDef={{
          sortable: true,
          resizable: true,
          suppressMovable: true,
          filter: true,
        }}
        domLayout="autoHeight"
        rowHeight={rowHeight}
        tooltipShowDelay={300}
        overlayNoRowsTemplate={`<span>${empty}</span>`}
      />
    </div>
  );
}

export function VerificationGrid({ rows }: { rows: AdminProject[] }) {
  const columns = useMemo<ColDef<AdminProject>[]>(
    () => [
      { field: "title", headerName: "Project", flex: 2, minWidth: 200 },
      { field: "category", width: 140 },
      { field: "region", width: 140 },
      {
        headerName: "Goal",
        colId: "goal",
        width: 120,
        valueGetter: (p) => p.data?.goal,
        valueFormatter: (p) => fmt(p.value ?? 0, p.data?.currency ?? "USD"),
      },
      {
        headerName: "Decision",
        colId: "actions",
        minWidth: 280,
        flex: 1.5,
        sortable: false,
        filter: false,
        cellRenderer: ({
          data,
          context,
        }: ICellRendererParams<AdminProject, unknown, Ctx>) =>
          data && (
            <Actions
              notify={context.notify}
              buttons={[
                {
                  label: "Verify",
                  tone: "primary",
                  run: () => verifyAction(data.id, true),
                },
                {
                  label: "Send back",
                  tone: "plain",
                  confirm: `Send "${data.title}" back to the applicant?`,
                  run: () => verifyAction(data.id, false),
                },
              ]}
            />
          ),
      },
    ],
    [],
  );
  return (
    <Grid
      rows={rows}
      columns={columns}
      empty="No projects waiting for review."
    />
  );
}

export function CasesGrid({ rows }: { rows: AdminCase[] }) {
  const columns = useMemo<ColDef<AdminCase>[]>(
    () => [
      {
        field: "projectTitle",
        headerName: "Project",
        flex: 1.5,
        minWidth: 180,
      },
      {
        field: "rule",
        headerName: "Rule hit",
        width: 170,
        valueFormatter: (p) => words(p.value ?? ""),
      },
      {
        field: "evidence",
        headerName: "Evidence",
        flex: 2,
        minWidth: 240,
        valueFormatter: (p) =>
          p.value
            ? Object.entries(p.value as Record<string, unknown>)
                .map(([k, v]) => `${words(k)}: ${String(v)}`)
                .join(" · ")
            : "",
        tooltipValueGetter: (p) => JSON.stringify(p.data?.evidence, null, 2),
      },
      {
        field: "createdAt",
        headerName: "Opened",
        width: 140,
        valueFormatter: (p) => when(p.value),
      },
      {
        headerName: "Decision",
        colId: "actions",
        minWidth: 300,
        flex: 1.5,
        sortable: false,
        filter: false,
        cellRenderer: ({
          data,
          context,
        }: ICellRendererParams<AdminCase, unknown, Ctx>) =>
          data && (
            <Actions
              notify={context.notify}
              buttons={[
                {
                  label: "Clear",
                  tone: "plain",
                  confirm: "False alarm? Matching resumes for this project.",
                  run: () => resolveCaseAction(data.id, "clear"),
                },
                {
                  label: "Confirm fraud",
                  tone: "danger",
                  confirm:
                    "Confirm? The flagged donors will count as one person in matching. This can't be undone here.",
                  run: () => resolveCaseAction(data.id, "confirm"),
                },
                {
                  label: "Confirm + remove",
                  tone: "danger",
                  confirm: "Confirm and remove the project? It is delisted and its donations are refunded.",
                  run: () => confirmAndRemoveAction(data.id),
                },
              ]}
            />
          ),
      },
    ],
    [],
  );
  return <Grid rows={rows} columns={columns} empty="No open Watchdog cases." />;
}

export function MilestonesGrid({ rows }: { rows: AdminMilestone[] }) {
  const columns = useMemo<ColDef<AdminMilestone>[]>(
    () => [
      { field: "title", headerName: "Milestone", flex: 2, minWidth: 220 },
      { field: "seq", headerName: "#", width: 70 },
      {
        headerName: "Tranche",
        colId: "amount",
        width: 120,
        valueGetter: (p) => p.data?.amount,
        valueFormatter: (p) => fmt(p.value ?? 0, p.data?.currency ?? "USD"),
      },
      {
        headerName: "Of which match",
        colId: "match",
        width: 150,
        valueGetter: (p) => p.data?.match,
        valueFormatter: (p) => fmt(p.value ?? 0, p.data?.currency ?? "USD"),
      },
      {
        headerName: "Decision",
        colId: "actions",
        minWidth: 280,
        flex: 1.5,
        sortable: false,
        filter: false,
        cellRenderer: ({
          data,
          context,
        }: ICellRendererParams<AdminMilestone, unknown, Ctx>) =>
          data && (
            <Actions
              notify={context.notify}
              buttons={[
                {
                  label: "Release",
                  tone: "primary",
                  confirm: `Release ${fmt(data.amount, data.currency)} to the project through PayPal Payouts?`,
                  run: () => reviewMilestoneAction(data.id, true),
                },
                {
                  label: "Ask for new evidence",
                  tone: "plain",
                  run: () => reviewMilestoneAction(data.id, false),
                },
              ]}
            />
          ),
      },
    ],
    [],
  );
  return (
    <Grid
      rows={rows}
      columns={columns}
      empty="No tranches waiting for an admin."
    />
  );
}

const actorLabel: Record<string, string> = {
  giving_agent: "Giving Agent",
  milestone_agent: "Milestone Agent",
  watchdog: "Watchdog",
  discovery: "Discovery",
  admin: "Admin",
};

export function AuditGrid({ rows }: { rows: AuditEntry[] }) {
  const [actor, setActor] = useState("all");
  const actors = useMemo(
    () => [...new Set(rows.map((r) => r.actor))].sort(),
    [rows],
  );
  const shown = actor === "all" ? rows : rows.filter((r) => r.actor === actor);
  const columns = useMemo<ColDef<AuditEntry>[]>(
    () => [
      {
        field: "createdAt",
        headerName: "When",
        width: 140,
        sort: "desc",
        valueFormatter: (p) => when(p.value),
      },
      {
        field: "actor",
        headerName: "Who",
        width: 150,
        valueFormatter: (p) => actorLabel[p.value] ?? words(p.value ?? ""),
      },
      {
        field: "action",
        headerName: "Action",
        width: 180,
        valueFormatter: (p) => words(p.value ?? ""),
      },
      {
        field: "ruleResult",
        headerName: "Rule result",
        width: 170,
        valueFormatter: (p) => words(p.value ?? "–"),
      },
      {
        field: "reason",
        headerName: "Reason",
        flex: 2,
        minWidth: 260,
        wrapText: true,
        autoHeight: true,
        valueFormatter: (p) => (p.value ? plainReport(String(p.value)) : ""),
        cellStyle: { lineHeight: "1.5", paddingTop: 16, paddingBottom: 16, whiteSpace: "pre-line" },
      },
      {
        colId: "trace",
        headerName: "Trace",
        width: 110,
        // Same rule as the public API: a run id in the inputs links to its public trace
        valueGetter: (p) => {
          const i = p.data?.inputs as Record<string, unknown> | null | undefined;
          const id = Number(i?.mandate_run_id ?? i?.run_id);
          return Number.isInteger(id) && id > 0 ? id : null;
        },
        cellRenderer: (p: { value: number | null }) =>
          p.value ? (
            <a href={`/agents?run=${p.value}`} className="font-bold text-primary underline">
              Run #{p.value}
            </a>
          ) : null,
      },
      {
        field: "inputs",
        headerName: "Inputs",
        flex: 1,
        minWidth: 180,
        valueFormatter: (p) => (p.value ? JSON.stringify(p.value) : ""),
        tooltipValueGetter: (p) => JSON.stringify(p.data?.inputs, null, 2),
      },
    ],
    [],
  );
  return (
    <div className="space-y-3">
      <div
        role="group"
        aria-label="Filter by who acted"
        className="flex flex-wrap gap-2"
      >
        {["all", ...actors].map((a) => (
          <button
            key={a}
            type="button"
            onClick={() => setActor(a)}
            aria-pressed={actor === a}
            className={`min-h-11 border px-4 text-sm ${actor === a ? "border-brand bg-brand text-white" : "border-line bg-white text-ink hover:border-brand"}`}
          >
            {a === "all" ? "Everyone" : (actorLabel[a] ?? words(a))}
          </button>
        ))}
      </div>
      <Grid
        rows={shown}
        columns={columns}
        empty="No agent actions logged yet. They appear here as the agents run."
      />
    </div>
  );
}
