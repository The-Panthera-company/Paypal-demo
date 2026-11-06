"use client";

import { useState, useTransition } from "react";
import { lookupDonationAction, refundAction } from "@/app/admin/actions";
import { Banner, Confirm, notify } from "@/components/Status";
import type { DonationInfo, RefundResult } from "@/lib/admin";

const field = "min-h-11 border border-line bg-white px-3 text-sm text-ink";

// Refunds: look up a donation by id (receipt numbers on My Impact), choose all or part, give a
// reason, confirm. Only captured PayPal payments can be refunded (NOT_REFUNDABLE otherwise).
export function RefundPanel() {
  const [id, setId] = useState("");
  const [donation, setDonation] = useState<DonationInfo | null>(null);
  const [dollars, setDollars] = useState("");
  const [reason, setReason] = useState("");
  const [asking, setAsking] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "error" | "info"; text: string } | null>(null);
  const [pending, start] = useTransition();
  const money = (c: number, cur = donation?.currency ?? "USD") => new Intl.NumberFormat(undefined, { style: "currency", currency: cur }).format(c / 100);
  const cents = dollars ? Math.round(Number(dollars) * 100) : undefined;
  const amountOk = cents === undefined || (cents > 0 && (!donation || cents <= donation.amount));

  const lookup = () =>
    start(async () => {
      setMsg(null);
      setDonation(null);
      const r = await lookupDonationAction(Number(id));
      if (r.ok) setDonation(r.donation);
      else setMsg({ tone: "error", text: r.message });
    });

  const refund = () =>
    start(async () => {
      if (!donation) return;
      const r = await refundAction(donation.id, reason.trim(), cents);
      if (!r.ok) {
        setMsg({ tone: "error", text: r.message });
        notify(r.message, "error");
        return;
      }
      const res: RefundResult = r.result;
      const text =
        res.paypal_status === "PENDING"
          ? "PayPal is processing the refund; totals update when it completes."
          : `Refunded ${money(res.amount_cents)} (${money(res.refunded_total_cents)} refunded in total). Donation is now ${res.donation_status}.`;
      setMsg({ tone: res.paypal_status === "PENDING" ? "info" : "success", text });
      notify(text, "success");
      setDonation({ ...donation, status: res.donation_status });
      setDollars("");
      setReason("");
    });

  return (
    <section className="space-y-5 bg-white p-6">
      <div>
        <h2 className="text-2xl">Refund a donation</h2>
        <p className="mt-1 text-sm">Find the donation by its id (the receipt number on My Impact). Only captured PayPal payments can be refunded; agent gifts paid from a balance can&apos;t.</p>
      </div>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (id) lookup();
        }}
      >
        <label className="flex flex-col text-sm text-ink">
          Donation id
          <input value={id} onChange={(e) => setId(e.target.value.replace(/\D/g, ""))} inputMode="numeric" className={`${field} w-40`} placeholder="e.g. 12" />
        </label>
        <button className="btn btn-2 !min-h-11 disabled:opacity-50" disabled={!id || pending}>
          Look up
        </button>
      </form>

      {donation && (
        <div className="space-y-4 border-t border-line pt-4">
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            {[
              ["Donation", `#${donation.id}`],
              ["Amount", money(donation.amount)],
              ["Status", donation.status],
              ["For", donation.projectId ? `project ${donation.projectId}` : donation.targetType.toLowerCase()],
            ].map(([k, v]) => (
              <div key={k} className="bg-surface-alt p-3">
                <dt className="text-xs uppercase tracking-[2px]">{k}</dt>
                <dd className="font-medium text-ink">{v}</dd>
              </div>
            ))}
          </dl>
          <div className="grid gap-3 sm:grid-cols-[200px_1fr]">
            <label className="flex flex-col text-sm text-ink">
              Amount ($, blank = all)
              <input type="number" min="0.01" step="0.01" value={dollars} onChange={(e) => setDollars(e.target.value)} aria-invalid={!amountOk} className={field} placeholder={String(donation.amount / 100)} />
            </label>
            <label className="flex flex-col text-sm text-ink">
              Reason (required, kept in the audit log)
              <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} className={field} placeholder="Donor asked" />
            </label>
          </div>
          <button type="button" onClick={() => setAsking(true)} disabled={!reason.trim() || !amountOk || pending} className="min-h-11 bg-cat-health px-5 text-sm font-bold text-white disabled:opacity-50">
            {pending ? "Working…" : `Refund ${cents ? money(cents) : "everything left"}`}
          </button>
        </div>
      )}

      {msg && <Banner tone={msg.tone}>{msg.text}</Banner>}

      <Confirm
        open={asking}
        title="Refund this donation?"
        body={
          <>
            {cents ? money(cents) : "Everything not refunded yet"} goes back to the donor through PayPal. It leaves the project&apos;s totals and matching. Reason: “{reason}”.
          </>
        }
        confirmLabel="Refund"
        danger
        onCancel={() => setAsking(false)}
        onConfirm={() => {
          setAsking(false);
          refund();
        }}
      />
    </section>
  );
}
