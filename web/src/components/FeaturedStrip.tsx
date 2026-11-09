"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
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
  const shown = Array.from({ length: windowSize }, (_, k) => ({ ...items[(offset + k) % n], pos: k }));
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
    <>
    <PhoneStrip items={items} />
    <div className="hidden space-y-3 md:block">
      <ul
        className="flex snap-x snap-mandatory gap-1 overflow-x-auto md:h-[480px] md:overflow-hidden"
        aria-label="Featured projects"
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        {shown.map(({ project: p, photo, raised, goal, days, pos }) => {
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
              {/* Brief info at the top of every panel: cause, title, place */}
              <div className="absolute inset-x-5 top-5" aria-hidden={on ? true : undefined}>
                <span className={`block text-[11px] font-bold uppercase leading-4 tracking-[2px] ${on ? "text-accent" : "text-cobalt-green"}`}>
                  {p.categoryId} · {p.facets.region}
                </span>
                {!on && <span className="mt-2 block font-display text-xl leading-6 text-white [overflow-wrap:anywhere]">{p.title}</span>}
                {!on && <span className="mt-2 block text-xs text-white/75">{pct}% funded</span>}
              </div>
              <div
                className={`absolute bottom-0 left-0 w-[min(100%,560px)] p-6 transition-all duration-500 md:p-8 ${
                  on && !shifting ? "opacity-100 md:translate-y-0 md:delay-300" : "opacity-100 md:pointer-events-none md:translate-y-4 md:opacity-0"
                }`}
              >
                <h3 className="max-w-md text-3xl leading-tight text-white">{p.title}</h3>
                <p className="mt-2 line-clamp-2 max-w-md text-sm leading-6 text-white/90">
                  {p.summary || `${p.facets.cause[0].toUpperCase()}${p.facets.cause.slice(1)} for ${p.facets.group.toLowerCase()} in ${p.facets.region}.`}
                </p>
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
          <span>{hover ? "Paused while you look" : paused ? "Paused" : "Moving through every project"}</span>
        </div>
      )}
    </div>
    </>
  );
}

const PHONE_STEP = 6000;

// Phones and small tablets: one project fills the area, a slim bar on the right shows where you are
// and fills while it waits, then the next one comes in. Tap the left or right edge to go back or on.
function PhoneStrip({ items }: { items: StripItem[] }) {
  const n = items.length;
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const [reduce, setReduce] = useState(false);
  const [visible, setVisible] = useState(true);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setReduce(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    const el = box.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting));
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const auto = !paused && !reduce && visible && n > 1;
  useEffect(() => {
    if (!auto) return;
    const t = setTimeout(() => setI((x) => (x + 1) % n), PHONE_STEP);
    return () => clearTimeout(t);
  }, [auto, i, n]);

  const go = (d: number) => setI((x) => (x + d + n) % n);
  const { project: p, photo, raised, goal, days } = items[i];
  const pct = Math.min(100, Math.round((p.raised.amount / p.goal.amount) * 100));

  return (
    <div className="space-y-3 md:hidden">
      <div ref={box} className="relative h-[min(560px,72vh)] overflow-hidden bg-ink text-white" role="group" aria-roledescription="carousel" aria-label="Featured projects">
        <div key={p.id} className="absolute inset-0 motion-safe:animate-[showcase-in_.5s_ease-out]">
          <CategoryArt id={p.categoryId} seed={p.id} photo={photo} tint={false} label={`Photo for ${p.title}`} />
        </div>
        <div className="absolute inset-0 bg-[linear-gradient(0deg,rgba(11,46,51,0.95)_10%,rgba(11,46,51,0.25)_60%,rgba(11,46,51,0.55))]" aria-hidden />

        {/* Tap zones: left edge = previous, right edge = next (buttons, so keyboards and screen readers get them too) */}
        <button type="button" onClick={() => go(-1)} className="absolute inset-y-0 left-0 z-10 w-[22%]" aria-label="Previous project" />
        <button type="button" onClick={() => go(1)} className="absolute inset-y-0 right-0 z-10 w-[22%]" aria-label="Next project" />

        {/* Slim bar on the right: the marker shows where you are in the list and fills while it waits */}
        <div className="pointer-events-none absolute bottom-6 right-2 top-6 z-20 w-1 bg-white/25" aria-hidden>
          <div className="absolute inset-x-0 min-h-7 overflow-hidden bg-white/40 transition-[top] duration-500" style={{ top: `${(i / n) * 100}%`, height: `${100 / n}%` }}>
            <span
              key={`${i}-${auto}`}
              className={`absolute inset-x-0 top-0 bg-accent ${auto ? "h-0 animate-[strip-fill_linear_forwards]" : "h-full"}`}
              style={auto ? { animationDuration: `${PHONE_STEP}ms` } : undefined}
            />
          </div>
        </div>

        <div className="absolute inset-x-0 top-0 p-5 pr-8">
          <span className="text-[11px] font-bold uppercase tracking-[2px] text-accent">
            {p.categoryId} · {p.facets.region}
          </span>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 p-5 pr-8" aria-live={auto ? "off" : "polite"}>
          <p className="text-xs text-white/70">
            {i + 1} of {n}
          </p>
          <h3 className="mt-1 text-[28px] leading-tight text-white">{p.title}</h3>
          <p className="mt-2 line-clamp-2 text-sm leading-6 text-white/90">
            {p.summary || `${p.facets.cause} for ${p.facets.group.toLowerCase()} in ${p.facets.region}.`}
          </p>
          <p className="mt-3 text-sm text-white/85">
            <strong className="tabular text-accent">{raised}</strong> of {goal} · {p.backerCount} backers · {days} days left
          </p>
          <div className="mt-3 h-1.5 bg-white/20" aria-hidden>
            <div className="h-full bg-cobalt-green" style={{ width: `${Math.max(pct, 1)}%` }} />
          </div>
          <Link href={`/projects/${p.id}`} className="btn pointer-events-auto mt-4 w-full justify-center" aria-label={`Back ${p.title}`}>
            Back this project
          </Link>
        </div>
      </div>
      {n > 1 && !reduce && (
        <button type="button" onClick={() => setPaused((x) => !x)} aria-pressed={paused} className="flex min-h-11 items-center gap-2 border border-line bg-white px-4 text-sm font-medium text-ink">
          <span aria-hidden>{paused ? "▶" : "❚❚"}</span> {paused ? "Play" : "Pause"}
        </button>
      )}
    </div>
  );
}
