"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Project } from "@/lib/types";
import { CategoryArt } from "./ui";

export type ShowcaseItem = { project: Project; photo: string; raised: string; goal: string; days: number };

const INTERVAL = 6000; // ms each project stays in focus
const STACK = 3; // background cards visible behind the focused one

// Full-screen explore preview: one project in focus over its own photo, the next ones stacked
// behind it. Every few seconds the first background card moves forward into focus. Pauses while
// pointed at or focused, has a pause button (WCAG 2.2.2) and stays still for reduced motion.
// Rotates through every project it is given, not a fixed handful.
export function ProjectShowcase({ items }: { items: ShowcaseItem[] }) {
  const [i, setI] = useState(0);
  const [hovering, setHovering] = useState(false);
  const [userPaused, setUserPaused] = useState(false);
  const [reduce, setReduce] = useState(false);
  const n = items.length;
  const next = useCallback(() => setI((v) => (v + 1) % n), [n]);
  const prev = useCallback(() => setI((v) => (v - 1 + n) % n), [n]);
  const root = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => setReduce(window.matchMedia("(prefers-reduced-motion: reduce)").matches), []);
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.3 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  const running = n > 1 && visible && !hovering && !userPaused && !reduce;
  useEffect(() => {
    if (!running) return;
    const t = setTimeout(next, INTERVAL);
    return () => clearTimeout(t);
  }, [running, next, i]);

  if (n === 0) return null;
  const cur = items[i];
  const pct = (it: ShowcaseItem) => Math.min(100, Math.round((it.project.raised.amount / it.project.goal.amount) * 100));
  const stack = Array.from({ length: Math.min(STACK, n - 1) }, (_, k) => items[(i + k + 1) % n]);

  return (
    <section
      ref={root}
      className="relative isolate flex min-h-[calc(100svh-5rem)] items-center overflow-hidden bg-ink pb-28 pt-16 text-white lg:min-h-[calc(100svh-110px)]"
      aria-roledescription="carousel"
      aria-label="Projects you can back"
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      onFocus={() => setHovering(true)}
      onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setHovering(false)}
    >
      {/* Backgrounds: current, previous and next photos only (a large pool stays light); the current one fades in */}
      {items.map((it, k) => ((k - i + n) % n <= 1 || (i - k + n) % n === 1) && (
        <div key={it.project.id} className={`absolute inset-0 -z-10 transition-opacity duration-1000 ${k === i ? "opacity-100" : "opacity-0"}`} aria-hidden>
          <div className={`size-full transition-transform duration-[7000ms] ease-out ${k === i && running ? "scale-110" : "scale-100"}`}>
            <CategoryArt id={it.project.categoryId} seed={it.project.id} photo={it.photo} tint={false} />
          </div>
        </div>
      ))}
      <div className="absolute inset-0 -z-10 bg-[linear-gradient(100deg,rgba(11,46,51,0.95)_30%,rgba(11,46,51,0.55)_65%,rgba(11,46,51,0.8))]" aria-hidden />

      <div className="container-k grid w-full items-center gap-12 lg:grid-cols-[1.1fr_1fr]">
        {/* Focused project */}
        <div key={cur.project.id} className="animate-[showcase-in_.7s_ease-out]" aria-live={running ? "off" : "polite"}>
          <div>
            <p className="eyebrow !text-cobalt-green">Explore projects · {String(i + 1).padStart(2, "0")} / {String(n).padStart(2, "0")}</p>
          </div>
          <span className="mt-4 inline-block bg-primary px-3 text-[11px] font-bold uppercase leading-6 tracking-[3px]">{cur.project.categoryId}</span>
          <h2 className="mt-4 max-w-xl text-4xl leading-tight text-white lg:text-6xl">{cur.project.title}</h2>
          <p className="mt-4 max-w-lg text-lg leading-8 text-white/85">{cur.project.summary}</p>
          <p className="mt-6 text-sm text-cobalt-green">
            {cur.project.facets.region} · {cur.project.backerCount} backers · {cur.days} days left
          </p>
          <div className="mt-3 max-w-lg">
            <div className="flex justify-between text-sm">
              <span className="tabular">
                <strong className="text-accent">{cur.raised}</strong> of {cur.goal}
              </span>
              <span className="tabular">{pct(cur)}%</span>
            </div>
            <div className="mt-2 h-2 bg-white/20" role="progressbar" aria-label={`${cur.project.title} funding progress`} aria-valuenow={pct(cur)} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full bg-cobalt-green transition-[width] duration-700" style={{ width: `${Math.max(1, pct(cur))}%` }} />
            </div>
          </div>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link href={`/projects/${cur.project.id}`} className="btn">
              Back this project
            </Link>
            <Link href="/projects" className="btn btn-2 border border-white/30">
              See all {n} projects
            </Link>
          </div>
        </div>

        {/* Background stack: the next projects, waiting to come forward */}
        <div className="relative hidden h-[460px] lg:block" aria-hidden>
          {stack.map((it, k) => (
            <button
              key={it.project.id}
              type="button"
              tabIndex={-1}
              onClick={() => setI((i + k + 1) % n)}
              className="absolute right-0 top-1/2 aspect-[4/5] w-[300px] overflow-hidden bg-ink text-left shadow-[0_25px_50px_rgba(0,0,0,0.45)] transition-all duration-700 ease-out"
              style={{
                transform: `translate(${-k * 70}px, -50%) scale(${1 - k * 0.08})`,
                zIndex: STACK - k,
                opacity: 1 - k * 0.22,
                filter: k === 0 ? "none" : `blur(${k}px) saturate(0.6)`,
              }}
            >
              <CategoryArt id={it.project.categoryId} seed={it.project.id} photo={it.photo} tint={false} />
              <span className="absolute inset-0 bg-[linear-gradient(180deg,transparent_45%,rgba(11,46,51,0.92))]" />
              <span className="absolute inset-x-0 bottom-0 p-5">
                <span className="block text-[11px] font-bold uppercase tracking-[3px] text-cobalt-green">Up next · {it.project.categoryId}</span>
                <span className="mt-1 block font-display text-2xl leading-7 text-white">{it.project.title}</span>
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Controls + progress */}
      <div className="absolute inset-x-0 bottom-8">
        <div className="container-k flex items-center gap-4">
          <button type="button" onClick={prev} className="grid size-12 place-items-center border border-white/30 hover:bg-white/10" aria-label="Previous project">
            ←
          </button>
          <button type="button" onClick={next} className="grid size-12 place-items-center border border-white/30 hover:bg-white/10" aria-label="Next project">
            →
          </button>
          <button
            type="button"
            onClick={() => setUserPaused((p) => !p)}
            className="grid size-12 place-items-center border border-white/30 hover:bg-white/10"
            aria-label={userPaused ? "Play the rotation" : "Pause the rotation"}
            aria-pressed={userPaused}
          >
            {userPaused ? "▶" : "❚❚"}
          </button>
          <div className="ml-2 h-0.5 flex-1 bg-white/20" aria-hidden>
            <div key={`${i}-${running}`} className={`h-full bg-accent ${running ? "animate-[showcase-progress_6s_linear]" : ""}`} style={{ width: running ? undefined : "0%" }} />
          </div>
        </div>
      </div>
    </section>
  );
}
