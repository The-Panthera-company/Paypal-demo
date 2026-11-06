"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const DONOR_ID = process.env.NEXT_PUBLIC_DEMO_DONOR_ID ?? "1";

// The open round's id, fetched once per page (null: no open round, so no preview)
let roundPromise: Promise<number | null> | null = null;
export function currentRoundId() {
  roundPromise ??= fetch(`${API_URL}/rounds/current`)
    .then((r) => (r.ok ? r.json() : null))
    .then((r: { id: number } | null) => r?.id ?? null)
    .catch(() => null);
  return roundPromise;
}

export type PreviewItem = { project_id: number; title: string; match_before_cents: number; match_after_cents: number; match_added_cents: number };

/** GET /rounds/{id}/match-preview. null = hide (no open round, project not matched, bad amount, network). */
export async function fetchMatchPreview(amountCents: number, projectId?: string, signal?: AbortSignal): Promise<{ currency: string; items: PreviewItem[] } | null> {
  if (!API_URL) return null;
  const round = await currentRoundId();
  if (!round) return null;
  const q = new URLSearchParams({ amount_cents: String(amountCents), donor_id: DONOR_ID });
  if (projectId) q.set("project_id", projectId);
  try {
    const r = await fetch(`${API_URL}/rounds/${round}/match-preview?${q}`, { signal });
    if (!r.ok) return null; // 409 ROUND_NOT_OPEN, 404 PROJECT_NOT_MATCHED, 422 AMOUNT_OUT_OF_RANGE: show nothing
    const d = (await r.json()) as { currency: string; items: PreviewItem[] };
    return d;
  } catch {
    return null;
  }
}

// "Your $5 adds about $38 of matching to New Reading Corner." Quadratic funding in one line:
// the same gift moves a little-backed project's match far more than a popular one's.
export function MatchPreview({ projectId, title, amountCents, valid }: { projectId: string; title: string; amountCents: number; valid: boolean }) {
  const [item, setItem] = useState<PreviewItem | null>(null);
  const [currency, setCurrency] = useState("USD");
  useEffect(() => {
    if (!valid) return setItem(null); // never call with an invalid amount (422)
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      const d = await fetchMatchPreview(amountCents, projectId, ctrl.signal);
      if (ctrl.signal.aborted) return;
      setCurrency(d?.currency ?? "USD");
      setItem(d?.items.find((i) => String(i.project_id) === projectId) ?? null);
    }, 300);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [amountCents, projectId, valid]);

  if (!item) return null;
  const fmt = (c: number) => new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(c / 100);
  const gift = new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: amountCents % 100 ? 2 : 0 }).format(amountCents / 100);
  return (
    <p role="status" className="flex gap-3 border-l-4 border-growth bg-surface-alt p-3 text-sm text-ink">
      <span className="mt-0.5 shrink-0 font-bold text-growth" aria-hidden>
        ✦
      </span>
      <span>
        {item.match_added_cents > 0 ? (
          <>
            Your {gift} adds about <strong className="tabular">{fmt(item.match_added_cents)}</strong> of matching to {title}.
          </>
        ) : (
          <>This gift won&apos;t change the match right now: you&apos;re past the per-person cap, the project is at its cap, or it needs a few more backers before matching moves.</>
        )}
        <span className="block text-xs text-text">Estimate: the match is recalculated until the round closes.</span>
      </span>
    </p>
  );
}
