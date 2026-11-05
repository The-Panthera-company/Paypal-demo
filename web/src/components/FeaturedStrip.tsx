"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Project } from "@/lib/types";
import { CategoryArt } from "./ui";

export type StripItem = { project: Project; photo: string; raised: string; goal: string; days: number };

const VISIBLE = 5; // panels on screen
const STEP = 5000; // ms before the next panel opens
const SLIDE = 800; // ms for the strip to move one panel
const OPEN_AT = 1; // once the open panel reaches this position, the strip flows instead

// Doria-inspired featured strip, moving on its own:
// - one panel is open when you arrive; pointing at (or tabbing to) a panel opens it and pauses;
// - left alone, the next panel opens every few seconds; once the open one is near the middle the
//   whole strip flows left: the first panel slides out and a new project slides in on the right,
//   so it runs continuously through every project, not a fixed handful.
// Pause button (WCAG 2.2.2), no movement with reduced motion, swipeable row on phones.
export function FeaturedStrip({ items }: { items: StripItem[] }) {
  const n = items.length;
  const [offset, setOffset] = useState(0); // pool index of the first visible panel
  const [active, setActive] = useState(items[0]?.project.id ?? ""); // the open panel
  const [shifting, setShifting] = useState(false);
  const [hover, setHover] = useState(false);
  const [paused, setPaused] = useState(false);
  const [canMove, setCanMove] = useState(false);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 768px)");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setCanMove(desktop.matches && !reduce.matches);
    update();
    desktop.addEventListener("change", update);
    return () => desktop.removeEventListener("change", update);
  }, []);

  // Visible panels plus one waiting (width 0) on the right, wrapping round the pool
  const windowSize = Math.min(n, VISIBLE + 1);
  const shown = Array.from({ length: windowSize }, (_, k) => ({ ...items[(offset + k) % n], pos: k, poolIndex: (offset + k) % n }));
  const activePos = shown.findIndex((s) => s.project.id === active);

  const running = canMove && n > VISIBLE && !hover && !paused;
  useEffect(() => {
    if (!running || shifting) return;
    const t = setTimeout(() => {
      const next = shown[activePos + 1] ?? shown[0];
      setActive(next.project.id);
      if (activePos >= OPEN_AT) setShifting(true); // flow: first slides out, a new one slides in
    }, STEP);
    return () => clearTimeout(t);
  }, [running, shifting, activePos, shown]);

  useEffect(() => {
    if (!shifting) return;
    const t = setTimeout(() => {
      setOffset((o) => (o + 1) % n);
      setShifting(false);
    }, SLIDE);
    return () => clearTimeout(t);
  }, [shifting, n]);

  if (n === 0) return null;

  return (
    <div className="space-y-3">
      <ul
        className="flex snap-x snap-mandatory gap-1 overflow-x-auto md:h-[480px] md:overflow-hidden"
        aria-label="Featured projects"
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        {shown.map(({ project: p, photo, raised, goal, days, pos, poolIndex }) => {
          const on = p.id === active;
          const leaving = shifting && pos === 0;
          const waiting = pos === windowSize - 1 && n > VISIBLE;
          const grow = leaving ? 0 : waiting ? (shifting ? 1 : 0) : on ? 3.4 : 1;
          const pct = Math.min(100, Math.round((p.raised.amount / p.goal.amount) * 100));
          return (
            <li
              key={p.id}
              onMouseEnter={() => setActive(p.id)}
              onFocus={() => setActive(p.id)}
              aria-hidden={waiting && !shifting ? true : undefined}
              className={`group relative h-[440px] w-[82%] shrink-0 snap-start overflow-hidden bg-ink text-white md:h-auto md:w-auto md:min-w-0 md:shrink ${
                waiting && !shifting ? "md:invisible" : ""
              }`}
              style={{ flexGrow: canMove || !waiting ? grow : 0, flexBasis: 0, transition: `flex-grow ${on || leaving || waiting ? SLIDE : 700}ms ease-in-out` }}
            >
              <div className={`absolute inset-0 transition-[filter,transform] duration-700 ${on ? "md:scale-100 md:grayscale-0 md:brightness-100" : "md:scale-105 md:grayscale md:brightness-[0.55]"}`}>
                <CategoryArt id={p.categoryId} seed={p.id} photo={photo} tint={false} label={`Photo for ${p.title}`} />
              </div>
              <div
                className={`absolute inset-0 bg-[linear-gradient(90deg,rgba(11,46,51,0.88),rgba(11,46,51,0.15)_75%)] transition-opacity duration-500 ${on ? "opacity-100" : "opacity-100 md:opacity-0"}`}
                aria-hidden
              />
              <span className="tabular absolute left-5 top-4 font-display text-5xl" aria-hidden>
                {String(poolIndex + 1).padStart(2, "0")}
              </span>
              <span className={`absolute left-5 top-[84px] w-28 text-[11px] font-bold uppercase leading-4 tracking-[2px] ${on ? "text-accent" : "text-cobalt-green"}`} aria-hidden>
                {p.categoryId}
              </span>
              <div
                className={`absolute bottom-0 left-0 w-[min(100%,560px)] p-6 transition-all duration-500 md:p-8 ${
                  on && !shifting ? "opacity-100 md:translate-y-0 md:delay-300" : "opacity-100 md:pointer-events-none md:translate-y-4 md:opacity-0"
                }`}
              >
                <h3 className="max-w-md text-3xl leading-tight text-white">{p.title}</h3>
                <p className="mt-3 max-w-md text-sm text-white/85">
                  <strong className="tabular text-accent">{raised}</strong> of {goal} · {p.backerCount} backers · {days} days left
                </p>
                <div className="mt-3 h-1.5 max-w-md bg-white/20" aria-hidden>
                  <div className="h-full bg-cobalt-green" style={{ width: `${Math.max(pct, 1)}%` }} />
                </div>
                <Link href={`/projects/${p.id}`} className="btn mt-5 whitespace-nowrap max-sm:px-6" aria-label={`Back ${p.title}`}>
                  Back this project
                </Link>
              </div>
            </li>
          );
        })}
      </ul>
      {canMove && n > VISIBLE && (
        <div className="flex items-center gap-3 text-sm text-ink">
          <button
            type="button"
            onClick={() => setPaused((x) => !x)}
            aria-pressed={paused}
            className="flex min-h-11 items-center gap-2 border border-line bg-white px-4 font-medium hover:border-primary"
          >
            <span aria-hidden>{paused ? "▶" : "❚❚"}</span> {paused ? "Play" : "Pause"} the moving strip
          </button>
          <span>
            {n} projects · {hover ? "paused while you look" : paused ? "paused" : "moving"}
          </span>
        </div>
      )}
    </div>
  );
}
