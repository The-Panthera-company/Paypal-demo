"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { fetchProjectProcurements, money, PROCUREMENT_LABEL, requestPurchase, type Procurement, type ProcurementStatus } from "@/lib/procurement";
import { Banner, notify } from "./Status";

const field = "min-h-11 w-full border border-line bg-white px-3 text-sm text-ink";
type M = { id: number; seq?: number; title: string; amount_cents: number; status: string };

const ORDER: ProcurementStatus[] = ["requested", "proposed", "approved", "paid"];
const CHIP: Record<ProcurementStatus, string> = {
  requested: "bg-accent text-ink",
  proposed: "bg-primary-container text-ink",
  approved: "bg-primary text-white",
  paid: "bg-cobalt-green text-ink",
  failed: "bg-cat-health text-white",
  cancelled: "bg-line text-ink",
};

/** Owner side of managed purchases: ask for something to be bought from an open milestone, follow it. */
export function PurchaseRequests({ projectId, milestones, token }: { projectId: string; milestones: M[]; token: string }) {
  const [list, setList] = useState<Procurement[] | null>(null);
  // One active purchase per milestone: hide milestones that already have one (or were bought)
  const taken = new Set((list ?? []).filter((p) => p.status !== "cancelled").map((p) => p.milestone_id));
  const open = milestones.filter((m) => (m.status === "open" || m.status === "evidence_submitted") && !taken.has(m.id));
  const [loadError, setLoadError] = useState(false);
  const [milestone, setMilestone] = useState<number | "">(open[0]?.id ?? "");
  const [what, setWhat] = useState("");
  const [qty, setQty] = useState("1");
  const [max, setMax] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchProjectProcurements(projectId)
      .then((l) => {
        setList(l);
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
  }, [projectId]);

  useEffect(() => {
    load();
    // Follow the agent and the admin while the page is open (proposals and payments take seconds)
    const t = setInterval(() => !document.hidden && load(), 5000);
    return () => clearInterval(t);
  }, [load]);
  const firstOpen = open[0]?.id;
  useEffect(() => {
    if (firstOpen !== undefined && (milestone === "" || !open.some((m) => m.id === milestone))) setMilestone(firstOpen);
  }, [firstOpen, milestone, open]);

  const chosen = open.find((m) => m.id === milestone);
  const cents = Math.round(Number(max) * 100);
  const valid = !!chosen && what.trim().length > 0 && Number(qty) >= 1 && cents > 0 && token.trim().length > 0;

  return (
    <section className="space-y-5 bg-white p-6" aria-labelledby="purchases">
      <div>
        <h2 id="purchases" className="text-xl">Request a purchase</h2>
        <p className="mt-1 text-sm">
          Instead of receiving the money, let the platform buy it for you: the Procurement Agent picks an eligible supplier and pays them through PayPal. Big purchases wait for an admin.
        </p>
      </div>

      {open.length === 0 ? (
        <p className="text-sm">No milestone is open for purchases right now.</p>
      ) : (
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!valid || !chosen) return;
            setBusy(true);
            setError(null);
            try {
              await requestPurchase(projectId, token.trim(), { milestone_id: chosen.id, description: what.trim(), quantity: Number(qty), max_amount_cents: cents });
              notify("Purchase requested. The agent will propose a supplier.", "success");
              setWhat("");
              setMax("");
              load();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Request failed.");
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="flex flex-col gap-1 text-sm text-ink sm:col-span-2">
            Milestone
            <select value={milestone} onChange={(e) => setMilestone(Number(e.target.value))} className={field}>
              {open.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.seq ? `${m.seq}. ` : ""}
                  {m.title} · {money(m.amount_cents)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink sm:col-span-2">
            What to buy
            <input value={what} onChange={(e) => setWhat(e.target.value)} maxLength={500} placeholder="e.g. 40 Grade 3 reading books" className={field} />
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink">
            Quantity
            <input type="number" min={1} step={1} value={qty} onChange={(e) => setQty(e.target.value)} className={field} />
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink">
            Most it may cost (USD)
            <input type="number" min={1} step="0.01" value={max} onChange={(e) => setMax(e.target.value)} placeholder={chosen ? String(chosen.amount_cents / 100) : ""} className={field} />
          </label>
          {!token.trim() && <p className="text-sm text-cat-health sm:col-span-2">Enter your project token above first.</p>}
          {error && (
            <div className="sm:col-span-2">
              <Banner tone="error">{error}</Banner>
            </div>
          )}
          <div className="sm:col-span-2">
            <button className="btn btn-2 disabled:opacity-50" disabled={!valid || busy}>
              {busy ? "Sending…" : "Request purchase"}
            </button>
          </div>
        </form>
      )}

      <div className="space-y-3 border-t border-line pt-4">
        <h3 className="text-lg">Your purchases</h3>
        {loadError && <Banner tone="error">Couldn&apos;t load your purchases. Retrying…</Banner>}
        {list === null && !loadError ? (
          <div className="h-16 animate-pulse bg-line/60 motion-reduce:animate-none" role="status" aria-label="Loading purchases" />
        ) : list && list.length === 0 ? (
          <p className="text-sm">No purchase requests yet. A project can request one from its evidence page.</p>
        ) : (
          <ul className="space-y-3">
            {list?.map((p) => (
              <PurchaseCard key={p.id} p={p} title={milestones.find((m) => m.id === p.milestone_id)?.title} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function PurchaseCard({ p, title }: { p: Procurement; title?: string }) {
  const at = ORDER.indexOf(p.status);
  return (
    <li className="space-y-3 border border-line p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-ink">
          {p.description} <span className="text-sm font-normal text-text">· {title ?? `milestone ${p.milestone_id}`}</span>
        </p>
        <span className={`px-2 text-[11px] font-bold uppercase leading-6 tracking-wider ${CHIP[p.status]}`}>{PROCUREMENT_LABEL[p.status]}</span>
      </div>
      {at >= 0 && (
        <ol className="grid grid-cols-4 gap-1 text-[11px] font-bold uppercase tracking-wider" aria-label="Progress">
          {ORDER.map((s, i) => (
            <li key={s} className={`border-t-4 pt-1 ${i <= at ? "border-primary text-ink" : "border-line text-text"}`} aria-current={i === at ? "step" : undefined}>
              {PROCUREMENT_LABEL[s]}
            </li>
          ))}
        </ol>
      )}
      <p className="text-sm">
        Up to {money(p.max_amount_cents, p.currency)} for {p.quantity}
        {p.supplier_name && (
          <>
            {" "}· {p.supplier_name} proposed {money(p.amount_cents, p.currency)}
          </>
        )}
        {p.needs_approval && <> · waiting for an admin (above the automatic limit)</>}
      </p>
      {p.status === "failed" && p.error && <p className="text-sm text-cat-health">PayPal refused the payment ({p.error}). An admin can retry it.</p>}
      {p.status === "paid" && (
        <div className="space-y-2 bg-surface-alt p-3 text-sm">
          <p className="font-medium text-ink">
            Paid {money(p.amount_cents, p.currency)} to {p.supplier_name} through PayPal
            {p.paypal_batch_id && (
              <>
                {" "}· batch <code className="text-primary">{p.paypal_batch_id}</code>
              </>
            )}
          </p>
          {p.line_items.length > 0 && <LineItems p={p} />}
          {p.receipt_url && (
            <a href={p.receipt_url} target="_blank" rel="noopener noreferrer" className="inline-block font-bold text-primary underline-offset-4 hover:underline">
              PayPal receipt ↗
            </a>
          )}
        </div>
      )}
      {p.run_id && (
        <Link href={`/agents?run=${p.run_id}`} className="text-sm font-bold text-primary">
          See what the agent did →
        </Link>
      )}
    </li>
  );
}

export function LineItems({ p }: { p: Procurement }) {
  return (
    <table className="w-full text-left">
      <caption className="sr-only">Line items</caption>
      <thead>
        <tr className="text-xs text-text">
          <th scope="col" className="font-medium">Item</th>
          <th scope="col" className="text-right font-medium">Qty</th>
          <th scope="col" className="text-right font-medium">Each</th>
        </tr>
      </thead>
      <tbody>
        {p.line_items.map((l, i) => (
          <tr key={i} className="border-t border-line/70">
            <td>{l.description ?? "Item"}</td>
            <td className="tabular text-right">{l.quantity ?? ""}</td>
            <td className="tabular text-right">{l.unit_amount_cents != null ? money(l.unit_amount_cents, p.currency) : l.amount_cents != null ? money(l.amount_cents, p.currency) : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
