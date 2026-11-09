"use client";

import { useState, useTransition } from "react";
import { confirmAndRemoveAction, resolveCaseAction } from "@/app/admin/actions";
import { analyseRing, CollusionGraph, type Graph } from "@/components/CollusionGraph";
import { Confirm, notify } from "@/components/Status";
import type { AdminCase } from "@/lib/admin";

export function CollusionCases({ cases }: { cases: AdminCase[] }) {
  return (
    <div className="space-y-6">
      {cases.map((c) => (
        <RingCase key={c.id} c={c} />
      ))}
    </div>
  );
}

function RingCase({ c }: { c: AdminCase }) {
  const graph = c.evidence!.graph as Graph;
  const ids = (Array.isArray(c.evidence?.donor_ids) ? c.evidence!.donor_ids : []) as (number | string)[];
  const m = analyseRing(graph, ids).metrics;
  const [asking, setAsking] = useState<null | "clear" | "confirm" | "remove">(null);
  const [done, setDone] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const go = (k: "clear" | "confirm" | "remove") =>
    start(async () => {
      const r = k === "remove" ? await confirmAndRemoveAction(c.id) : await resolveCaseAction(c.id, k);
      notify(r.message, r.ok ? "success" : "error");
      if (r.ok) setDone(r.message);
      setAsking(null);
    });
  const ask = {
    clear: { title: "Clear this case?", body: "False alarm? Matching resumes for this project.", label: "Clear" },
    confirm: { title: "Confirm the ring?", body: "The flagged donors will count as one person in matching. This can't be undone here.", label: "Confirm" },
    remove: { title: "Confirm and remove the project?", body: "The project is delisted and its donations are refunded.", label: "Confirm + remove project" },
  };
  const metric = (k: string, v: string) => (
    <div className="bg-surface-alt p-3">
      <dt className="text-[11px] font-bold uppercase tracking-[2px] text-text">{k}</dt>
      <dd className="tabular font-display text-2xl text-ink">{v}</dd>
    </div>
  );

  return (
    <section className="space-y-4 bg-white p-6" aria-labelledby={`ring-${c.id}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 id={`ring-${c.id}`} className="text-xl">
          Possible ring around {c.projectTitle}
        </h3>
        <span className="bg-cat-health px-2 text-[11px] font-bold uppercase leading-6 tracking-wider text-white">Rule: collusion cluster</span>
      </div>
      <CollusionGraph graph={graph} clusterIds={ids} title={`Case ${c.id}`} />
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {metric("Donors", String(m.donors))}
        {metric("Projects", String(m.projects))}
        {metric("Shared projects", String(m.shared))}
        {metric("Ratio", `${Math.round(m.ratio * 100)}%`)}
        {metric("Total", m.total.toLocaleString())}
      </dl>
      <p className="text-sm text-ink">Confirm counts these donors as one person in matching; it does not refund or ban them.</p>
      {done ? (
        <p role="status" className="border-l-4 border-primary bg-surface-alt p-3 text-sm text-ink">{done}</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={pending} onClick={() => setAsking("clear")} className="min-h-11 border border-line bg-white px-4 text-xs font-bold uppercase tracking-wider text-ink hover:border-brand disabled:opacity-50">Clear</button>
          <button type="button" disabled={pending} onClick={() => setAsking("confirm")} className="min-h-11 bg-cat-health px-4 text-xs font-bold uppercase tracking-wider text-white disabled:opacity-50">Confirm</button>
          <button type="button" disabled={pending} onClick={() => setAsking("remove")} className="min-h-11 bg-ink px-4 text-xs font-bold uppercase tracking-wider text-white disabled:opacity-50">Confirm + remove project</button>
        </div>
      )}
      <Confirm
        open={asking !== null}
        danger={asking !== "clear"}
        title={asking ? ask[asking].title : ""}
        body={asking ? ask[asking].body : ""}
        confirmLabel={asking ? ask[asking].label : ""}
        onConfirm={() => asking && go(asking)}
        onCancel={() => setAsking(null)}
      />
    </section>
  );
}
