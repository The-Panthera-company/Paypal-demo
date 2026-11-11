"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import { runProcurementAgentAction, type ProcurementRunResult } from "@/app/admin/actions";

// Admin-only "Run now" for the Procurement Agent. The call happens in a server action.
export function RunProcurementAgent() {
  const [res, setRes] = useState<ProcurementRunResult | null>(null);
  const [pending, start] = useTransition();
  return (
    <section className="space-y-3 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl">Procurement Agent</h2>
          <p className="text-sm">Proposes suppliers for open requests and pays the ones within the automatic limit.</p>
        </div>
        <button type="button" disabled={pending} onClick={() => start(async () => setRes(await runProcurementAgentAction()))} className="btn btn-2 disabled:opacity-50">
          {pending ? "Running…" : "Run Procurement Agent"}
        </button>
      </div>
      {res && (
        <div role="status" className="space-y-2 border-t border-line pt-3 text-sm">
          {!res.ok ? (
            <p className="text-cat-health">{res.message}</p>
          ) : res.runs.length === 0 && res.abstained.length === 0 ? (
            <p className="font-medium text-ink">Nothing to buy: no open purchase requests.</p>
          ) : (
            <>
              {res.runs.length > 0 && (
                <div>
                  <p className="font-medium text-ink">Purchases made ({res.runs.length})</p>
                  <ul className="mt-1 space-y-1">
                    {res.runs.map((r, i) => (
                      <li key={r.runId ?? `r${i}`}>
                        {r.procurementId != null ? `Purchase #${r.procurementId}` : "Purchase"}
                        {r.summary && <> · {r.summary}</>}
                        {r.runId != null && (
                          <Link href={`/agents?run=${r.runId}`} className="ml-2 font-bold text-primary">
                            Trace →
                          </Link>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {res.abstained.length > 0 && (
                <div>
                  <p className="font-medium text-ink">Skipped ({res.abstained.length})</p>
                  <ul className="mt-1 space-y-1">
                    {res.abstained.map((a, i) => (
                      <li key={`a${i}`}>
                        {a.procurementId != null ? `Request #${a.procurementId}` : "A request"}
                        {a.reason && <span className="text-text"> · {a.reason.replaceAll("_", " ")}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
