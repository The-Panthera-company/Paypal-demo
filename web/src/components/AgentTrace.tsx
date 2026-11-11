"use client";

import Link from "next/link";
import { AgentReport } from "./AgentReport";
import type { AgentRun, TraceStep } from "@/lib/agent-trace";

const CHIP: Record<string, string> = {
  ok: "bg-cobalt-green text-ink",
  skipped: "bg-line text-ink",
  blocked: "bg-cat-health text-white",
  error: "bg-cat-health text-white",
  pending: "bg-accent text-ink",
};

// Small line icons per kind of step (search, score, rules check, record, write-up)
const ICON: Record<string, string> = {
  search: "M11 4a7 7 0 100 14 7 7 0 000-14zM20 20l-4-4",
  score: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  rule: "M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z",
  give: "M12 20s-7-4.4-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.6-7 10-7 10z",
  record: "M5 4h14v16H5zM9 8h6M9 12h6M9 16h3",
  report: "M4 5h16v10H9l-5 4z",
  skip: "M5 12h14M13 6l6 6-6 6",
};
function iconFor(s: TraceStep) {
  const k = `${s.step} ${s.tool ?? ""}`.toLowerCase();
  if (s.status === "blocked") return ICON.rule;
  if (s.status === "skipped") return ICON.skip;
  if (/search|candidate|list/.test(k)) return ICON.search;
  if (/score|rank/.test(k)) return ICON.score;
  if (/donation|give|allocat/.test(k)) return ICON.give;
  if (/report|explain/.test(k)) return ICON.report;
  if (/record|log|run/.test(k)) return ICON.record;
  return ICON.rule;
}

function Data({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || (typeof value === "object" && Object.keys(value as object).length === 0)) return null;
  return (
    <div>
      <p className="text-[11px] font-bold uppercase tracking-[2px] text-text">{label}</p>
      <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap break-words bg-surface-alt p-3 text-xs text-ink">{typeof value === "string" ? value : JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "");

/** One run's steps as a vertical timeline. `animate` makes steps appear one after another. */
export function AgentTrace({ run, animate = false, compact = false }: { run: AgentRun; animate?: boolean; compact?: boolean }) {
  const derived = run.trace.length === 0 && (run.chosen.length > 0 || run.skipped.length > 0);
  const steps = derived ? stepsFromDecisions(run) : [...run.trace].sort((a, b) => a.seq - b.seq);
  const fmt = (c: number) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(c / 100);
  return (
    <div className="space-y-5">
      {run.report_text && (
        <div className="border-l-4 border-primary bg-white p-4">
          <span className="mb-2 block text-[11px] font-bold uppercase tracking-[2px] text-primary">The agent&apos;s report</span>
          <AgentReport text={run.report_text} compact={compact} />
        </div>
      )}

      {derived && (
        <p className="text-xs text-text">Summary built from this run&apos;s recorded decisions. The agent didn&apos;t send a step-by-step trace for this run.</p>
      )}
      {steps.length === 0 ? (
        <p className="border border-dashed border-line bg-white p-4 text-sm">This run recorded no step-by-step trace.</p>
      ) : (
        <ol className="relative space-y-3 border-l-2 border-line pl-6" aria-label={`Steps of agent run ${run.id}`}>
          {steps.slice(0, compact ? 8 : undefined).map((s, i) => (
            <li
              key={s.seq}
              className={`relative ${animate ? "opacity-0 motion-safe:animate-[showcase-in_.4s_ease-out_forwards] motion-reduce:opacity-100" : ""}`}
              style={animate ? { animationDelay: `${i * 180}ms` } : undefined}
            >
              <span className={`absolute -left-[37px] top-2 grid size-6 place-items-center ring-4 ring-surface ${s.status === "blocked" || s.status === "error" ? "bg-cat-health text-white" : s.status === "skipped" ? "bg-line text-ink" : "bg-primary text-white"}`} aria-hidden>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d={iconFor(s)} />
                </svg>
              </span>
              <details className="group bg-white ring-1 ring-line open:ring-primary">
                <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 p-3 [&::-webkit-details-marker]:hidden">
                  <span className="min-w-0 flex-1 font-medium text-ink">{s.title}</span>
                  {s.status === "blocked" && s.rule && <span className="bg-cat-health px-2 text-[11px] font-bold uppercase leading-5 tracking-wider text-white">Rule: {s.rule}</span>}
                  {s.tool && <code className="bg-surface-alt px-1.5 text-xs text-primary">{s.tool}</code>}
                  <span className={`px-2 text-[11px] font-bold uppercase leading-5 tracking-wider ${CHIP[s.status] ?? CHIP.ok}`}>{s.status}</span>
                  <span className="tabular text-xs text-text">{time(s.at)}</span>
                  <span className="text-xs text-primary group-open:rotate-90" aria-hidden>
                    ▸
                  </span>
                </summary>
                <div className="space-y-3 border-t border-line p-3">
                  {s.reason && <p className="text-sm text-ink">{s.reason}</p>}
                  {s.rule && s.status !== "blocked" && <p className="text-xs">Rule result: <strong className="text-ink">{s.rule}</strong></p>}
                  <Data label="What it saw" value={s.input} />
                  <Data label="What came back" value={s.result} />
                  {s.actor && <p className="text-xs text-text">By {s.actor}</p>}
                </div>
              </details>
            </li>
          ))}
        </ol>
      )}

      {!compact && (run.chosen.length > 0 || run.skipped.length > 0) && (
        <div className="grid gap-4 md:grid-cols-2">
          <section className="bg-white p-4">
            <h3 className="text-lg">Chosen</h3>
            {run.chosen.length === 0 ? (
              <p className="text-sm">Nothing this time.</p>
            ) : (
              <ul className="mt-2 space-y-1 text-sm">
                {run.chosen.map((c, i) => (
                  <li key={c.project_id ?? `pending-${i}`} className="flex justify-between gap-3">
                    {c.project_id != null ? (
                      <Link href={`/projects/${c.project_id}`} className="text-ink hover:text-primary hover:underline">
                        {c.title ?? `Project ${c.project_id}`}
                      </Link>
                    ) : (
                      <span className="text-ink">{c.title ?? "Not proposed yet"}</span>
                    )}
                    <span className="tabular font-medium text-ink">{fmt(c.amount_cents)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="bg-white p-4">
            <h3 className="text-lg">Left out</h3>
            {run.skipped.length === 0 ? (
              <p className="text-sm">Nothing left out.</p>
            ) : (
              <ul className="mt-2 max-h-64 space-y-1 overflow-auto text-sm">
                {run.skipped.map((k, i) => (
                  <li key={`${k.project_id}-${i}`}>
                    <span className="text-ink">{k.title ?? (k.project_id ? `Project ${k.project_id}` : "A project")}</span>
                    {k.reason && <span className="text-text"> · {k.reason.replaceAll("_", " ")}</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {compact && (
        <Link href={`/agents?run=${run.id}`} className="inline-block text-sm font-bold uppercase tracking-[2px] text-primary">
          View full trace →
        </Link>
      )}
    </div>
  );
}

/** When a run has no detailed trace: a timeline from what it recorded (candidates, gifts, skips by reason, report) */
function stepsFromDecisions(run: AgentRun): TraceStep[] {
  const fmt = (c: number) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(c / 100);
  const steps: TraceStep[] = [];
  const add = (s: Omit<TraceStep, "seq" | "at" | "actor">) => steps.push({ seq: steps.length + 1, at: run.run_at, actor: "giving-agent", ...s });
  add({ step: "search", tool: "search_projects", status: "ok", title: `Read ${run.chosen.length + run.skipped.length} candidate projects in the donor's causes`, input: null, result: null, rule: null, reason: null });
  for (const c of run.chosen)
    add({ step: "request_donation", tool: "request_checked_donation", status: "ok", title: `Asked the rules engine for ${fmt(c.amount_cents)} to ${c.title ?? (c.project_id != null ? `project ${c.project_id}` : "a project")}`, input: { project_id: c.project_id, amount_cents: c.amount_cents }, result: null, rule: "ok", reason: null });
  const byReason = new Map<string, AgentRun["skipped"]>();
  for (const k of run.skipped) byReason.set(k.reason ?? "other", [...(byReason.get(k.reason ?? "other") ?? []), k]);
  for (const [reason, list] of byReason)
    add({
      step: "skip",
      tool: null,
      status: "skipped",
      title: `Left out ${list.length} project${list.length > 1 ? "s" : ""}: ${reason.replaceAll("_", " ")}`,
      input: null,
      result: list.slice(0, 12).map((k) => k.title ?? k.project_id),
      rule: reason,
      reason: reason === "budget_exhausted" ? "The agent only gives from money put into its balance, and the monthly budget was used up or empty." : null,
    });
  if (run.report_text) add({ step: "report", tool: "record_mandate_run", status: "ok", title: "Wrote the report for the donor and recorded the run", input: null, result: run.report_text, rule: null, reason: null });
  return steps;
}

/** Skeleton while a trace loads */
export function TraceSkeleton() {
  return (
    <div className="space-y-3 border-l-2 border-line pl-6" aria-label="Loading the agent trace" role="status">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="h-12 animate-pulse bg-line/60 motion-reduce:animate-none" />
      ))}
    </div>
  );
}
