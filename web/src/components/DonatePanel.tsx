"use client";

import { Banner, notify } from "@/components/Status";
import { PayPalButtons, PayPalScriptProvider } from "@paypal/react-paypal-js";
import { useEffect, useState } from "react";

// Flow 1 from the design doc: the PayPal button creates an order through the core API,
// the donor approves in PayPal, and the API captures it and writes the donation + ledger entry.
// The browser only sends the target and amount; the API decides what gets recorded.

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const PRESETS = [5, 10, 25, 50];

type PayPalConfig = {
  client_id: string;
  currency: string;
  environment: "sandbox" | "live";
  min_donation_cents: number;
  max_donation_cents: number;
};

type Status =
  | { kind: "idle" }
  | { kind: "done"; amountCents: number }
  | { kind: "cancelled" }
  | { kind: "error"; message: string };

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: { error?: string; message?: string } }).detail;
    const err = new Error(detail?.message ?? `Request failed (${res.status})`) as Error & { code?: string };
    err.code = detail?.error;
    throw err;
  }
  return data as T;
}

/** What the gift is for: one project, a whole category (split by the API), or the donor's Giving Agent budget */
export type DonationTarget =
  | { kind: "PROJECT"; projectId: string }
  | { kind: "CATEGORY"; categoryApiId: number; rule: "crowd" | "equal" | "closest_to_goal"; excludedTags: string[] }
  | { kind: "AGENT" };

function orderBody(target: DonationTarget, amountCents: number) {
  if (target.kind === "PROJECT") return { target_type: "PROJECT", project_id: Number(target.projectId), amount_cents: amountCents };
  if (target.kind === "CATEGORY")
    return { target_type: "CATEGORY", category_id: target.categoryApiId, amount_cents: amountCents, rule: target.rule, excluded_tags: target.excludedTags };
  return { target_type: "AGENT", amount_cents: amountCents };
}

export function DonatePanel({
  projectId,
  projectTitle,
  target,
  onAmountChange,
}: {
  projectId?: string;
  projectTitle: string;
  target?: DonationTarget;
  onAmountChange?: (cents: number) => void;
}) {
  const what: DonationTarget = target ?? { kind: "PROJECT", projectId: projectId ?? "" };
  const [config, setConfig] = useState<PayPalConfig | null>(null);
  const [configError, setConfigError] = useState(false);
  const [dollars, setDollars] = useState("10");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  useEffect(() => {
    if (!API_URL) return;
    fetch(`${API_URL}/config/paypal`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((c: PayPalConfig) => (c.client_id ? setConfig(c) : setConfigError(true)))
      .catch(() => setConfigError(true));
  }, []);

  const amountCents = Math.round(Number(dollars) * 100);
  useEffect(() => {
    onAmountChange?.(amountCents);
  }, [amountCents, onAmountChange]);
  const min = config?.min_donation_cents ?? 100;
  const max = config?.max_donation_cents ?? 100_000;
  const amountOk = Number.isFinite(amountCents) && amountCents >= min && amountCents <= max;
  const currency = config?.currency ?? "USD";
  const fmt = (cents: number) =>
    new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(cents / 100);

  if (status.kind === "done") {
    return (
      <div className="corner border border-line bg-white p-6" role="status">
        <p className="font-display text-2xl text-ink">Thank you!</p>
        <p className="mt-2">
          Your {fmt(status.amountCents)} gift to {projectTitle} is confirmed. It counts toward this round&apos;s matching
          pool, and you&apos;ll see receipts here when the next milestone is released.
        </p>
        <button type="button" className="btn btn-2 mt-4" onClick={() => setStatus({ kind: "idle" })}>
          Give again
        </button>
      </div>
    );
  }

  return (
    <div id="donate" className="space-y-4">
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-ink">Choose an amount ({currency})</legend>
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setDollars(String(v))}
              aria-pressed={dollars === String(v)}
              className={`min-h-12 min-w-16 border px-4 font-medium ${
                dollars === String(v) ? "border-brand bg-brand text-white" : "border-line bg-white text-ink hover:border-brand"
              }`}
            >
              {fmt(v * 100)}
            </button>
          ))}
          <label className="flex min-h-12 items-center border border-line bg-white px-3 focus-within:border-brand">
            <span className="sr-only">Other amount</span>
            <span aria-hidden className="mr-1 text-ink">
              Other
            </span>
            <input
              type="number"
              inputMode="decimal"
              min={min / 100}
              max={max / 100}
              step="1"
              value={dollars}
              onChange={(e) => setDollars(e.target.value)}
              className="w-20 bg-transparent text-ink focus:outline-none"
              aria-describedby="amount-help"
              aria-invalid={!amountOk}
            />
          </label>
        </div>
        <p id="amount-help" className={`mt-2 text-sm ${amountOk ? "" : "font-medium text-danger"}`}>
          {amountOk ? `Between ${fmt(min)} and ${fmt(max)}.` : `Enter an amount between ${fmt(min)} and ${fmt(max)}.`}
        </p>
      </fieldset>

      {status.kind === "error" && <Banner tone="error">{status.message} Nothing was charged.</Banner>}
      {status.kind === "cancelled" && <Banner tone="info">Payment cancelled. Nothing was charged.</Banner>}

      {!API_URL ? (
        <p className="border border-dashed border-line bg-white p-4 text-sm">
          Payments are off in sample-data mode. Set <code>NEXT_PUBLIC_API_URL</code> to the core API to give with PayPal
          sandbox.
        </p>
      ) : configError ? (
        <Banner tone="warning" title="PayPal isn't available right now">
          The API has no PayPal sandbox keys, or it can&apos;t be reached. Try again in a minute.
        </Banner>
      ) : !config ? (
        <div className="h-[150px] animate-pulse bg-line" aria-label="Loading PayPal" />
      ) : (
        <PayPalScriptProvider options={{ clientId: config.client_id, currency: config.currency, intent: "capture" }}>
          <PayPalButtons
            style={{ layout: "vertical", shape: "rect", label: "donate", height: 48 }}
            disabled={!amountOk}
            forceReRender={[amountCents, JSON.stringify(what)]}
            createOrder={async () => {
              setStatus({ kind: "idle" });
              const order = await post<{ order_id: string }>("/donations/orders", orderBody(what, amountCents));
              return order.order_id;
            }}
            onApprove={async (data, actions) => {
              try {
                const donation = await post<{ amount_cents: number; status: string }>(
                  `/donations/orders/${data.orderID}/capture`,
                );
                setStatus({ kind: "done", amountCents: donation.amount_cents });
                notify("Thank you! Your gift went through. PayPal will email your receipt.", "success");
              } catch (e) {
                const err = e as Error & { code?: string };
                if (err.code === "INSTRUMENT_DECLINED") return actions.restart();
                setStatus({ kind: "error", message: err.message });
                notify("The payment didn't go through. Nothing was charged.", "error");
              }
            }}
            onCancel={() => setStatus({ kind: "cancelled" })}
            onError={(err) =>
              setStatus({ kind: "error", message: err instanceof Error ? err.message : "PayPal reported a problem." })
            }
          />
        </PayPalScriptProvider>
      )}

      {config?.environment === "sandbox" && (
        <p className="text-xs">PayPal sandbox: use a sandbox buyer account. No real money moves.</p>
      )}
    </div>
  );
}
