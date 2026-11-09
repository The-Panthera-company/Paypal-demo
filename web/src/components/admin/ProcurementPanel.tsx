"use client";

import Link from "next/link";
import { Fragment, useState, useTransition } from "react";
import { retryProcurementAction, reviewProcurementAction } from "@/app/admin/actions";
import { LineItems } from "@/components/PurchaseRequests";
import { Confirm, notify } from "@/components/Status";
import type { AdminProcurement } from "@/lib/admin";
import { money, PROCUREMENT_LABEL } from "@/lib/procurement";

const CHIP: Record<string, string> = {
  requested: "bg-accent text-ink",
  proposed: "bg-primary-container text-ink",
  approved: "bg-primary text-white",
  paid: "bg-cobalt-green text-ink",
  failed: "bg-cat-health text-white",
  cancelled: "bg-line text-ink",
};

function age(iso: string) {
  const h = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  return h < 1 ? `${Math.max(1, Math.round(h * 60))} min` : h < 48 ? `${Math.round(h)} h` : `${Math.round(h / 24)} d`;
}

type Ask = { row: AdminProcurement; kind: "approve" | "reject" | "retry" };

export function ProcurementPanel({ rows }: { rows: AdminProcurement[] }) {
  const [openId, setOpenId] = useState<number | null>(null);
  const [ask, setAsk] = useState<Ask | null>(null);
  const [pending, start] = useTransition();

  const go = (a: Ask) =>
    start(async () => {
      const r = a.kind === "retry" ? await retryProcurementAction(a.row.id) : await reviewProcurementAction(a.row.id, a.kind === "approve");
      notify(r.message, r.ok ? "success" : "error");
      setAsk(null);
    });

  if (rows.length === 0)
    return <p className="border border-dashed border-line bg-white p-6">No purchase requests yet. A project can request one from its evidence page.</p>;

  const amountOf = (r: AdminProcurement) => money(r.amount_cents ?? r.max_amount_cents, r.currency);
  return (
    <div className="space-y-3">
      <p>Projects ask for something to be bought; the Procurement Agent proposes a supplier and pays it through PayPal. Anything above the automatic limit waits here.</p>
      <div className="overflow-x-auto bg-white">
        <table className="w-full min-w-[760px] text-left text-sm">
          <caption className="sr-only">Purchase requests</caption>
          <thead className="bg-ink text-white">
            <tr>
              {["Project", "Milestone", "Supplier", "Amount", "Status", "Age", "Decision"].map((h) => (
                <th key={h} scope="col" className="px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const isOpen = openId === r.id;
              const canDecide = r.status === "proposed" || r.status === "requested";
              return (
                <Fragment key={r.id}>
                  <tr className={`border-t border-line align-top ${r.needs_approval ? "bg-accent/30" : ""}`}>
                    <td className="px-3 py-2">
                      <button type="button" onClick={() => setOpenId(isOpen ? null : r.id)} aria-expanded={isOpen} className="text-left font-medium text-ink hover:text-primary">
                        <span aria-hidden className="mr-1 inline-block text-primary">{isOpen ? "▾" : "▸"}</span>
                        {r.projectTitle}
                      </button>
                      <span className="block text-xs text-text">{r.description}</span>
                    </td>
                    <td className="px-3 py-2">{r.milestoneTitle}</td>
                    <td className="px-3 py-2">{r.supplier_name ?? <span className="text-text">Not chosen yet</span>}</td>
                    <td className="tabular px-3 py-2 font-medium text-ink">
                      {amountOf(r)}
                      {r.amount_cents == null && <span className="block text-xs font-normal text-text">max</span>}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`px-2 text-[11px] font-bold uppercase leading-5 tracking-wider ${CHIP[r.status]}`}>{PROCUREMENT_LABEL[r.status]}</span>
                      {r.needs_approval && <span className="mt-1 block w-fit bg-ink px-2 text-[11px] font-bold uppercase leading-5 tracking-wider text-accent">Needs approval</span>}
                    </td>
                    <td className="tabular px-3 py-2">{age(r.created_at)}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {canDecide && r.status === "proposed" && (
                          <button type="button" disabled={pending} onClick={() => setAsk({ row: r, kind: "approve" })} className="min-h-9 bg-primary px-3 text-xs font-bold uppercase tracking-wider text-white disabled:opacity-50">
                            Approve
                          </button>
                        )}
                        {canDecide && (
                          <button type="button" disabled={pending} onClick={() => setAsk({ row: r, kind: "reject" })} className="min-h-9 border border-line px-3 text-xs font-bold uppercase tracking-wider text-ink disabled:opacity-50">
                            Reject
                          </button>
                        )}
                        {r.status === "failed" && (
                          <button type="button" disabled={pending} onClick={() => setAsk({ row: r, kind: "retry" })} className="min-h-9 bg-cat-health px-3 text-xs font-bold uppercase tracking-wider text-white disabled:opacity-50">
                            Retry
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-surface-alt">
                      <td colSpan={7} className="space-y-3 px-5 py-4">
                        <p>
                          <strong className="text-ink">Asked for:</strong> {r.quantity} × {r.description}, at most {money(r.max_amount_cents, r.currency)}
                        </p>
                        {r.rationale && (
                          <p>
                            <strong className="text-ink">Why this supplier:</strong> {r.rationale}
                          </p>
                        )}
                        {r.line_items.length > 0 && (
                          <div className="max-w-lg bg-white p-3">
                            <LineItems p={r} />
                          </div>
                        )}
                        <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                          <div>
                            <dt className="inline font-medium text-ink">Quote: </dt>
                            <dd className="inline">{r.line_items.length ? "line items above" : "none sent"}</dd>
                          </div>
                          <div>
                            <dt className="inline font-medium text-ink">PayPal batch: </dt>
                            <dd className="inline"><code className="text-primary">{r.paypal_batch_id ?? "—"}</code></dd>
                          </div>
                          <div>
                            <dt className="inline font-medium text-ink">Receipt: </dt>
                            <dd className="inline">
                              {r.receipt_url ? (
                                <a href={r.receipt_url} target="_blank" rel="noopener noreferrer" className="text-primary underline">
                                  open ↗
                                </a>
                              ) : (
                                "—"
                              )}
                            </dd>
                          </div>
                          {r.error && (
                            <div>
                              <dt className="inline font-medium text-cat-health">Last error: </dt>
                              <dd className="inline">{r.error}</dd>
                            </div>
                          )}
                        </dl>
                        <Link href={r.run_id ? `/agents?run=${r.run_id}` : `/projects/${r.project_id}`} className="inline-block text-sm font-bold text-primary">
                          {r.run_id ? "Agent trace →" : "Project page →"}
                        </Link>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <Confirm
        open={ask !== null}
        danger={ask?.kind !== "approve"}
        title={ask ? (ask.kind === "approve" ? `Approve ${amountOf(ask.row)}?` : ask.kind === "reject" ? `Reject ${amountOf(ask.row)}?` : `Retry ${amountOf(ask.row)}?`) : ""}
        body={
          ask
            ? ask.kind === "approve"
              ? `${ask.row.supplier_name ?? "The supplier"} can then be paid ${amountOf(ask.row)} through PayPal by the agent for "${ask.row.description}" (${ask.row.projectTitle}).`
              : ask.kind === "reject"
                ? `The request for "${ask.row.description}" is cancelled. Nothing is paid; the project can ask again.`
                : `PayPal is sent the same batch again, so the supplier can't be paid twice.`
            : ""
        }
        confirmLabel={ask ? (ask.kind === "approve" ? "Approve" : ask.kind === "reject" ? "Reject" : "Retry payment") : ""}
        onConfirm={() => ask && go(ask)}
        onCancel={() => setAsk(null)}
      />
    </div>
  );
}
