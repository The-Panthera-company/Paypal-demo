"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { LAND } from "@/lib/globe-land";

// Per dot, computed once: sin(lat), cos(lat), lng in radians (the per-frame work is one cos/sin)
const DOTS = (() => {
  const out = new Float32Array((LAND.length / 2) * 3);
  for (let i = 0, j = 0; i < LAND.length; i += 2, j += 3) {
    const la = (LAND[i] * Math.PI) / 180;
    out[j] = Math.sin(la);
    out[j + 1] = Math.cos(la);
    out[j + 2] = (LAND[i + 1] * Math.PI) / 180;
  }
  return out;
})();

export type GlobePin = { id: string; title: string; categoryId: string; location: [number, number]; raised: string; goal: string; place: string };

type Group = { key: string; location: [number, number]; place: string; pins: GlobePin[] };

const SPEED = 0.005; // radians per frame (~15 fps): slow, a backdrop not a show
const TILT = -0.3; // lift the equator (where most projects are) above the faded bottom edge

// Orthographic projection shared by the dots and the HTML pins, so pins sit exactly on the globe.
function project([lat, lng]: [number, number], phi: number) {
  const la = (lat * Math.PI) / 180;
  const lo = (lng * Math.PI) / 180 + phi;
  const x = Math.cos(la) * Math.sin(lo);
  const y0 = Math.sin(la);
  const z0 = Math.cos(la) * Math.cos(lo);
  const y = y0 * Math.cos(TILT) - z0 * Math.sin(TILT);
  const z = y0 * Math.sin(TILT) + z0 * Math.cos(TILT);
  return { x, y, z };
}

// A slowly turning dotted globe in the site's teal, drawn on a 2D canvas (works on every device), with a pin per project location.
// Pins are HTML buttons (keyboard and screen-reader reachable) moved every frame by direct
// DOM writes, never React state, so the animation can't trigger re-render loops.
export function GlobeBackdrop({ pins, className = "" }: { pins: GlobePin[]; className?: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const pinEls = useRef<(HTMLDivElement | null)[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const paused = useRef(false);

  const groups = useMemo<Group[]>(() => {
    const m = new Map<string, Group>();
    for (const p of pins) {
      const key = p.location.join(",");
      const g = m.get(key) ?? { key, location: p.location, place: p.place, pins: [] };
      g.pins.push(p);
      m.set(key, g);
    }
    return [...m.values()];
  }, [pins]);

  useEffect(() => {
    paused.current = open !== null;
  }, [open]);

  useEffect(() => {
    const el = canvas.current;
    const wrap = box.current;
    const ctx = el?.getContext("2d");
    if (!el || !wrap || !ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Start with the first project's longitude facing slightly left of centre
    let phi = groups[0] ? -((groups[0].location[1] * Math.PI) / 180) + 0.5 : 0;
    let visible = true;
    let raf = 0;
    let running = false;
    // Fully stopped while scrolled away or on another tab: no timer, no pulsing pins.
    // Picks up where it left off (same angle) when it comes back into view.
    const stop = () => {
      running = false;
      window.clearTimeout(raf);
      pinEls.current.forEach((d) => d && (d.dataset.live = "false"));
    };
    const start = () => {
      if (running || !visible || document.hidden) return;
      running = true;
      draw();
    };
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (visible) start();
      else stop();
    });
    io.observe(wrap);
    const onVis = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", onVis);

    // ~15 fps: wake on a timer, then draw in the next animation frame
    const tick = () => {
      raf = window.setTimeout(() => running && requestAnimationFrame(draw), 66);
    };
    const draw = () => {
      if (!running) return;
      tick();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = wrap.offsetWidth;
      if (el.width !== Math.round(w * dpr)) {
        el.width = el.height = Math.round(w * dpr);
      }
      const R = (w / 2) * 0.86;
      const c = w / 2;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, w);
      // Soft glow and a dark sphere
      const glow = ctx.createRadialGradient(c, c, R * 0.9, c, c, R * 1.12);
      glow.addColorStop(0, "rgba(150,209,170,0.18)");
      glow.addColorStop(1, "rgba(150,209,170,0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, w, w);
      const body = ctx.createRadialGradient(c - R * 0.35, c - R * 0.4, R * 0.1, c, c, R);
      body.addColorStop(0, "rgba(0,113,144,0.55)");
      body.addColorStop(1, "rgba(11,46,51,0.85)");
      ctx.fillStyle = body;
      ctx.beginPath();
      ctx.arc(c, c, R, 0, Math.PI * 2);
      ctx.fill();
      // Land dots, fading towards the edge: 4 brightness bands, one path and one fill each
      const cT = Math.cos(TILT), sT = Math.sin(TILT);
      const bands = [new Path2D(), new Path2D(), new Path2D(), new Path2D()];
      for (let i = 0; i < DOTS.length; i += 3) {
        const lo = DOTS[i + 2] + phi;
        const z0 = DOTS[i + 1] * Math.cos(lo);
        const y0 = DOTS[i];
        const z = y0 * sT + z0 * cT;
        if (z <= 0) continue;
        const x = DOTS[i + 1] * Math.sin(lo);
        const y = y0 * cT - z0 * sT;
        const b = Math.min(3, (z * 4) | 0);
        const sz = 1.2 + b * 0.35;
        bands[b].rect(c + x * R - sz / 2, c - y * R - sz / 2, sz, sz);
      }
      bands.forEach((path, b) => {
        ctx.fillStyle = `rgba(150,209,170,${0.2 + b * 0.18})`;
        ctx.fill(path);
      });
      // Pins: move the HTML elements directly (no React state per frame)
      groups.forEach((g, i) => {
        const d = pinEls.current[i];
        if (!d) return;
        const p = project(g.location, phi);
        // Pins show only once well onto the front (z > 0.45), fade in to 0.65, and pulse only
        // near the centre (z > 0.75): the globe may show no pins at all for a while.
        const front = p.z > 0.45;
        const live = p.z > 0.75;
        if (d.dataset.live !== String(live)) d.dataset.live = String(live);
        d.style.transform = `translate(${c + p.x * R}px, ${c - p.y * R}px) translate(-50%, -50%)`;
        d.style.opacity = front ? String(Math.round(Math.min(1, (p.z - 0.45) * 5) * 10) / 10) : "0";
        // Only touch focusability when a pin turns to the front or the back
        if (d.dataset.front !== String(front)) {
          d.dataset.front = String(front);
          d.style.pointerEvents = front ? "auto" : "none";
          const btn = d.firstElementChild as HTMLButtonElement | null;
          if (btn) btn.tabIndex = front ? 0 : -1;
        }
      });
      if (!reduce && !paused.current) phi += SPEED;
    };
    start();
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVis);
      io.disconnect();
    };
  }, [groups]);

  return (
    <div ref={box} className={`relative aspect-square ${className}`} onMouseLeave={() => setOpen(null)}>
      <canvas ref={canvas} className="block size-full" aria-hidden />
      {groups.map((g, i) => (
        <div
          key={g.key}
          ref={(d) => {
            pinEls.current[i] = d;
          }}
          className={`absolute left-0 top-0 opacity-0 transition-opacity duration-300 ${open === i ? "z-20" : "z-10"}`}
        >
          <button
            type="button"
            className="group relative grid size-7 place-items-center"
            aria-label={`${g.pins.length} project${g.pins.length > 1 ? "s" : ""} in ${g.place}`}
            aria-expanded={open === i}
            onMouseEnter={() => setOpen(i)}
            onFocus={() => setOpen(i)}
            onClick={() => setOpen(open === i ? null : i)}
          >
            <span className="absolute size-4 bg-accent/40 opacity-0 group-hover:scale-150 [[data-live=true]_&]:animate-ping [[data-live=true]_&]:opacity-100" aria-hidden />
            <span className="size-2.5 bg-accent ring-2 ring-ink" aria-hidden />
          </button>
          {open === i && (
            <div
              role="tooltip"
              onMouseEnter={() => setOpen(i)}
              className="absolute bottom-full left-1/2 mb-1 w-60 -translate-x-1/2 bg-white p-3 text-left text-ink shadow-[0_10px_30px_rgba(0,0,0,0.3)]"
            >
              <span className="block text-[11px] font-bold uppercase tracking-[2px] text-primary">{g.place}</span>
              {g.pins.slice(0, 3).map((p) => (
                <Link key={p.id} href={`/projects/${p.id}`} className="mt-2 block border-t border-line pt-2 hover:text-primary">
                  <span className="block font-medium leading-5">{p.title}</span>
                  <span className="tabular text-xs text-text">
                    {p.raised} of {p.goal} · <span className="capitalize">{p.categoryId}</span>
                  </span>
                </Link>
              ))}
              {g.pins.length > 3 && <span className="mt-2 block text-xs">+{g.pins.length - 3} more</span>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
