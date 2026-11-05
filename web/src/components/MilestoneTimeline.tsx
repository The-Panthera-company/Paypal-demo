"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import type { Milestone } from "@/lib/types";

// Bryntum is browser-only and large, so it loads on its own after the page has shown.
const MilestoneGantt = dynamic(() => import("./MilestoneGantt"), {
  ssr: false,
  loading: () => <div className="h-[260px] animate-pulse bg-line" aria-label="Loading timeline" />,
});

const statusText: Record<Milestone["status"], string> = {
  open: "Not started",
  evidence_submitted: "Evidence being checked",
  held: "Held for an admin",
  released: "Released",
};

export function MilestoneTimeline({ milestones }: { milestones: Milestone[] }) {
  if (milestones.length === 0) return null;
  const fmt = (m: Milestone) =>
    new Intl.NumberFormat(undefined, { style: "currency", currency: m.amount.currency, maximumFractionDigits: 0 }).format(m.amount.amount / 100);
  const dated = milestones.every((m) => m.dueDate);

  return (
    <section className="space-y-4">
      <h2 className="text-3xl">Milestone plan</h2>
      <p className="max-w-[65ch]">
        Money is released in tranches. Each one needs receipts and photos that pass the checks before it is paid, and this
        round&apos;s matching is added to the next tranche.
      </p>
      {dated ? (
        <WhenVisible>
          <MilestoneGantt milestones={milestones} />
        </WhenVisible>
      ) : (
        // No due dates yet: a plain list rather than invented dates
        <ol className="divide-y divide-line border border-line bg-white">
          {[...milestones]
            .sort((a, b) => a.seq - b.seq)
            .map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-4 p-4">
                <span className="tabular font-display text-2xl text-primary">{m.seq}</span>
                <span className="flex-1 font-medium text-ink">{m.title}</span>
                <span className="tabular font-bold text-ink">{fmt(m)}</span>
                <span className="text-sm">{statusText[m.status]} · date not set yet</span>
              </li>
            ))}
        </ol>
      )}
    </section>
  );
}

// Bryntum keeps working in the background once mounted (measured: ~56% CPU on a slow phone while
// hidden in a closed tab). Mount it only while it is on screen; a placeholder keeps the space.
function WhenVisible({ children }: { children: React.ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setOn(e.isIntersecting), { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <div ref={box} className="min-h-[260px]">
      {on ? children : <div className="h-[260px] bg-line/50" aria-label="Milestone timeline" />}
    </div>
  );
}
