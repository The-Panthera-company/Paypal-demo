"use client";

import { useRef, useState } from "react";
import { CategoryArt, Eyebrow } from "./ui";

type Tab = { id: string; label: string; body: string; points: string[]; art: string };

const TABS: Tab[] = [
  {
    id: "mission",
    label: "Our mission",
    body: "Let many small donors decide together where help goes, and prove where every dollar went. The number of people who back a project matters more than the size of any one gift.",
    points: ["Verified projects only", "Matching that rewards many backers", "Money released in tranches, with receipts", "Agents check, people decide"],
    art: "mission",
  },
  {
    id: "vision",
    label: "Our vision",
    body: "A world where a $5 gift from a thousand people carries more weight than one large cheque, and where anyone can see what their money changed, wherever they live.",
    points: ["Open to projects in any country", "Privacy first: donors are anonymous by default", "Every decision explained in plain words", "Fixed rules, never a black box"],
    art: "vision",
  },
  {
    id: "history",
    label: "Our history",
    body: "Community Giving started in November 2026 as a three-person project for the PayPal AI Hackathon: one person on the core API and matching engine, one on this website, one on the AI agents.",
    points: [
      "Day 1: design and the two-level quadratic matching rules",
      "First sandbox donation through PayPal",
      "Watchdog and Giving Agent join, with an admin console",
      "Milestone releases with evidence, and My Impact",
    ],
    art: "history",
  },
];

// "Get to know us": mission, vision and history as tabs (keyboard: arrow keys move between tabs).
export function PlatformIdentity() {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const t = TABS[active];

  const onKey = (e: React.KeyboardEvent) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    const n = (active + d + TABS.length) % TABS.length;
    setActive(n);
    refs.current[n]?.focus();
  };

  return (
    <section className="section">
      <div className="container-k space-y-10">
        <div className="grid gap-8 lg:grid-cols-2">
          <div>
            <Eyebrow>Get to know Community Giving</Eyebrow>
            <h2 className="section-title">Giving decided by the crowd</h2>
          </div>
          <p className="self-end text-lg leading-8">
            We built a place where giving is fair, open and checked at every step: agents read and flag, fixed rules move the money, and PayPal handles every payment.
          </p>
        </div>

        <div role="tablist" aria-label="About the platform" className="flex flex-wrap gap-2" onKeyDown={onKey}>
          {TABS.map((x, k) => (
            <button
              key={x.id}
              ref={(b) => {
                refs.current[k] = b;
              }}
              role="tab"
              id={`tab-${x.id}`}
              aria-selected={k === active}
              aria-controls={`panel-${x.id}`}
              tabIndex={k === active ? 0 : -1}
              onClick={() => setActive(k)}
              className={`corner min-h-12 px-6 font-bold transition-colors ${k === active ? "bg-ink text-white" : "bg-cobalt-green text-ink hover:bg-primary hover:text-white"}`}
              style={{ ["--corner-size" as string]: k === active ? "10px" : "0px" }}
            >
              {x.label}
            </button>
          ))}
        </div>

        <div role="tabpanel" id={`panel-${t.id}`} aria-labelledby={`tab-${t.id}`} key={t.id} className="grid animate-[showcase-in_.5s_ease-out] gap-10 lg:grid-cols-2">
          <p className="text-lg leading-9">{t.body}</p>
          <div className="grid gap-6 sm:grid-cols-[220px_1fr]">
            <div className="aspect-square">
              <CategoryArt id="people" seed={t.art} label={`${t.label} picture`} />
            </div>
            <ul className="space-y-3 self-center">
              {t.points.map((p) => (
                <li key={p} className="flex gap-3 text-ink">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-brand)" strokeWidth="3" className="mt-1 shrink-0" aria-hidden>
                    <path d="M4 12l5 5L20 6" />
                  </svg>
                  {p}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
