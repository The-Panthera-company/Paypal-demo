"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const DONOR_ID = process.env.NEXT_PUBLIC_DEMO_DONOR_ID ?? "1";
const PRESETS = [10, 25, 50];

type Status = "APPROVAL_PENDING" | "ACTIVE" | "SUSPENDED" | "CANCELLED" | "EXPIRED";
type Sub = { subscription_id: string; monthly_amount_cents: number; currency: string; status: Status; approve_url: string | null };
type ApiError = { status: number; code?: string; message?: string };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, { ...init, headers: { "Content-Type": "application/json" }, cache: "no-store" });
  if (r.ok) return r.json() as Promise<T>;
  const body = await r.json().catch(() => null);
  throw { status: r.status, code: body?.detail?.error, message: body?.detail?.message } as ApiError;
}

const dollars = (cents: number, cur = "USD") =>
  new Intl.NumberFormat(undefined, { style: "currency", currency: cur, maximumFractionDigits: cents % 100 ? 2 : 0 }).format(cents / 100);

// Monthly giving: a PayPal subscription that funds the Giving Agent.
// Redirect flow (no PayPal SDK here: vault/intent=subscription clashes with the capture script on other pages).
export function MonthlyGiving() {
  const [sub, setSub] = useState<Sub | null>(null);
  const [loading, setLoading] = useState(true);
  const [amount, setAmount] = useState(25);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [balance, setBalance] = useState<number | null>(null);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await call<Sub>(`/donors/${DONOR_ID}/mandate/subscription`);
      setSub(s);
      return s;
    } catch (e) {
      if ((e as ApiError).status !== 404) setNotice({ ok: false, text: "Couldn't load your monthly giving. Refresh to try again." });
      setSub(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const loadBalance = useCallback(async () => {
    try {
      const m = await call<{ funded_balance_cents?: number }>(`/donors/${DONOR_ID}/mandate`);
      if (typeof m.funded_balance_cents === "number") setBalance(m.funded_balance_cents);
    } catch {
      /* no mandate yet */
    }
  }, []);

  useEffect(() => {
    if (!API_URL) {
      setLoading(false);
      return;
    }
    const back = new URLSearchParams(window.location.search).get("subscription");
    if (back) window.history.replaceState(null, "", window.location.pathname);
    load().then((s) => {
      if (s?.status === "ACTIVE") loadBalance();
      if (back === "cancelled") setNotice({ ok: true, text: "No problem, nothing was set up." });
      if (back === "approved") {
        setNotice({ ok: true, text: "Monthly giving is set up. Waiting for PayPal to confirm…" });
        if (s?.status === "ACTIVE") return setNotice({ ok: true, text: "Monthly giving is set up." });
        // PayPal's webhook switches it to ACTIVE; check every 3 s for up to 30 s
        setWaiting(true);
        let tries = 0;
        poll.current = setInterval(async () => {
          tries++;
          const next = await load();
          if (next?.status === "ACTIVE" || tries >= 10) {
            if (poll.current) clearInterval(poll.current);
            setWaiting(false);
            if (next?.status === "ACTIVE") {
              setNotice({ ok: true, text: "Monthly giving is set up." });
              loadBalance();
            } else {
              setNotice({ ok: true, text: "PayPal is still confirming. This page will show it as active once it does." });
            }
          }
        }, 3000);
      }
    });
    return () => {
      if (poll.current) clearInterval(poll.current);
    };
  }, [load, loadBalance]);

  function explain(e: ApiError) {
    // fetch() itself failing (offline, server error without CORS headers) has no status
    if (!("status" in e)) e = { status: 0 };
    if (e.status === 409 || e.code === "ALREADY_SUBSCRIBED") {
      load();
      return { ok: true, text: "You already give monthly." };
    }
    if (e.status === 422 || e.code === "WHOLE_DOLLARS_ONLY") return { ok: false, text: e.message ?? "Please use a whole-dollar amount." };
    if (!e.status || e.status >= 500) return { ok: false, text: "PayPal had a problem. Please try again in a moment." };
    return { ok: false, text: e.message ?? "Something went wrong. Please try again." };
  }

  async function start() {
    if (!Number.isInteger(amount) || amount < 1) return setNotice({ ok: false, text: "Please use a whole-dollar amount of at least $1." });
    setBusy(true);
    setNotice(null);
    try {
      const s = await call<Sub>(`/donors/${DONOR_ID}/mandate/subscription`, {
        method: "POST",
        body: JSON.stringify({ monthly_amount_cents: amount * 100 }),
      });
      if (s.approve_url) {
        window.location.href = s.approve_url;
        return;
      }
      setSub(s);
    } catch (e) {
      setNotice(explain(e as ApiError));
    }
    setBusy(false);
  }

  async function cancel() {
    setBusy(true);
    try {
      const s = await call<Sub>(`/donors/${DONOR_ID}/mandate/subscription/cancel`, { method: "POST" });
      setSub(s);
      setNotice({ ok: true, text: "Monthly giving is cancelled. Nothing more will be charged." });
    } catch (e) {
      setNotice(explain(e as ApiError));
    }
    setConfirming(false);
    setBusy(false);
  }

  const status = sub?.status;
  const live = status === "ACTIVE" || status === "SUSPENDED";

  return (
    <section className="space-y-5 bg-white p-6" aria-labelledby="monthly-title" aria-busy={loading || waiting}>
      <div>
        <h2 id="monthly-title" className="text-2xl">Monthly giving</h2>
        <p className="mt-1 max-w-[65ch]">Fund your Giving Agent automatically each month through PayPal. Cancel any time.</p>
      </div>

      {!API_URL && <p className="text-sm">Connect the core API to set up monthly giving.</p>}
      {loading && API_URL && <div className="h-24 animate-pulse bg-line" aria-label="Loading" />}

      {!loading && live && sub && (
        <div className="space-y-3">
          {status === "ACTIVE" ? (
            <p className="font-display text-2xl text-ink">{dollars(sub.monthly_amount_cents, sub.currency)}/month to your Giving Agent</p>
          ) : (
            <p className="border-l-4 border-danger bg-surface-alt p-3 text-ink">
              PayPal paused this, usually a failed payment. Update your payment method in PayPal, or cancel below.
            </p>
          )}
          {balance !== null && <p className="text-sm">Agent balance ready to give: <strong className="tabular text-ink">{dollars(balance, sub.currency)}</strong></p>}
          {confirming ? (
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-ink">Stop giving {dollars(sub.monthly_amount_cents, sub.currency)} every month?</span>
              <button type="button" className="btn-2" onClick={cancel} disabled={busy}>Yes, cancel</button>
              <button type="button" className="min-h-12 px-4 font-medium text-ink underline" onClick={() => setConfirming(false)}>Keep it</button>
            </div>
          ) : (
            <button type="button" className="min-h-12 border border-line px-5 font-medium text-ink hover:border-primary" onClick={() => setConfirming(true)}>
              Cancel monthly giving
            </button>
          )}
        </div>
      )}

      {!loading && API_URL && !live && !waiting && (
        <div className="space-y-4">
          {status === "APPROVAL_PENDING" && (
            <p className="border-l-4 border-growth bg-surface-alt p-3 text-ink">Finish setting up in PayPal. Pressing the button again starts a fresh attempt.</p>
          )}
          <fieldset>
            <legend className="mb-2 font-medium text-ink">Amount each month (whole dollars)</legend>
            <div className="flex flex-wrap items-center gap-2">
              {PRESETS.map((p) => (
                <button
                  key={p}
                  type="button"
                  aria-pressed={amount === p}
                  onClick={() => setAmount(p)}
                  className={`min-h-12 min-w-16 border px-4 font-bold ${amount === p ? "border-primary bg-primary text-white" : "border-line text-ink hover:border-primary"}`}
                >
                  ${p}
                </button>
              ))}
              <label className="flex min-h-12 items-center border border-line px-3">
                <span className="text-ink">$</span>
                <span className="sr-only">Other amount</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={1}
                  step={1}
                  value={amount || ""}
                  onChange={(e) => setAmount(Math.floor(Number(e.target.value)))}
                  className="w-20 px-1 text-ink outline-none"
                />
              </label>
            </div>
          </fieldset>
          <button type="button" className="btn" onClick={start} disabled={busy || amount < 1}>
            {busy ? "Opening PayPal…" : `Give $${amount || 0} every month with PayPal`}
          </button>
          <p className="text-xs">You&apos;ll approve it on PayPal (sandbox), then come back here.</p>
        </div>
      )}

      {notice && (
        <p role={notice.ok ? "status" : "alert"} className={`text-sm ${notice.ok ? "font-medium text-ink" : "font-medium text-danger"}`}>
          {notice.text}
        </p>
      )}
    </section>
  );
}
