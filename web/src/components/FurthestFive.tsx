"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchMatchPreview, type PreviewItem } from "./MatchPreview";

// "Where $5 goes furthest": one match-preview call for every project (or a category's projects),
// top three by matching added. Hidden when there's no open round.
export function FurthestFive({ projectIds, amountCents = 500 }: { projectIds?: string[]; amountCents?: number }) {
  const [items, setItems] = useState<PreviewItem[] | null>(null);
  const [currency, setCurrency] = useState("USD");
  const key = projectIds?.join(",");
  useEffect(() => {
    const ctrl = new AbortController();
    fetchMatchPreview(amountCents, undefined, ctrl.signal).then((d) => {
      if (!d || ctrl.signal.aborted) return;
      const allow = key ? new Set(key.split(",")) : null;
      setCurrency(d.currency);
      setItems(d.items.filter((i) => i.match_added_cents > 0 && (!allow || allow.has(String(i.project_id)))).slice(0, 3));
    });
    return () => ctrl.abort();
  }, [amountCents, key]);
  if (!items?.length) return null;
  const fmt = (c: number) => new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(c / 100);
  return (
    <section aria-labelledby="furthest" className="bg-ink p-5 text-white">
      <h2 id="furthest" className="flex items-center gap-2 text-xl text-white">
        <span className="text-accent" aria-hidden>
          ✦
        </span>
        Where {fmt(amountCents)} goes furthest right now
      </h2>
      <ol className="mt-3 grid gap-3 sm:grid-cols-3">
        {items.map((i, k) => (
          <li key={i.project_id}>
            <Link href={`/projects/${i.project_id}`} className="flex h-full items-start gap-3 bg-white/10 p-3 hover:bg-white/15">
              <span className="tabular grid size-8 shrink-0 place-items-center bg-accent font-bold text-ink">{k + 1}</span>
              <span>
                <span className="block font-medium leading-5">{i.title}</span>
                <span className="text-sm text-cobalt-green">
                  +<strong className="tabular text-accent">{fmt(i.match_added_cents)}</strong> of matching
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-white/70">Estimates: few backers means each new backer moves the match most. Recalculated until the round closes.</p>
    </section>
  );
}
