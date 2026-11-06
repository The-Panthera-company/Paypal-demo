"use client";

import { useState } from "react";
import { DonatePanel } from "./DonatePanel";
import { RollingNumber } from "./RollingNumber";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

// "Add to the matching pool": sponsors (a business, a club, anyone) top up the open round's pool.
// It isn't a project gift: no backer is added and it doesn't count on the donor ladders.
export function SponsorPool({ poolCents, currency = "USD" }: { poolCents?: number; currency?: string }) {
  const [name, setName] = useState("");
  const [pool, setPool] = useState(poolCents);
  const fmt = (c: number) => new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(c / 100);
  const refresh = () =>
    fetch(`${API_URL}/rounds/current`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((r: { matching_pool_cents: number } | null) => r && setPool(r.matching_pool_cents))
      .catch(() => undefined);

  return (
    <section id="sponsor" aria-labelledby="sponsor-title" className="grid gap-8 bg-ink p-6 text-white lg:grid-cols-[1fr_420px] lg:p-10">
      <div className="space-y-4">
        <p className="eyebrow !text-cobalt-green">For businesses, clubs and anyone</p>
        <h2 id="sponsor-title" className="text-3xl text-white lg:text-4xl">
          Add to the matching pool
        </h2>
        <p className="max-w-xl text-white/85">
          Your money joins this round&apos;s pool and is shared by how many people back each project, so it multiplies small gifts everywhere. It isn&apos;t a project gift: you won&apos;t appear on the donor ladders.
        </p>
        {pool !== undefined && (
          <p className="text-lg">
            Pool now: <strong className="font-display text-3xl text-accent"><RollingNumber key={pool} value={fmt(pool)} /></strong>
          </p>
        )}
        <label className="block max-w-sm text-sm">
          Sponsor name (optional, leave blank to stay anonymous)
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className="mt-1 min-h-11 w-full border border-white/30 bg-white/10 px-3 text-white placeholder:text-white/50" placeholder="Nakuru Rotary Club" />
        </label>
        <p className="text-xs text-white/60">Up to $10,000 per payment. Only while a round is open.</p>
      </div>
      <div className="bg-white p-5 text-ink">
        <DonatePanel projectTitle="the matching pool" target={{ kind: "POOL", sponsorName: name }} onDone={refresh} />
      </div>
    </section>
  );
}
