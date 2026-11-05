"use client";

import { useEffect, useRef, useState } from "react";

// Odometer-style number: each digit is a wheel of 0-9 that rolls up to its value when the number
// comes into view (or when it changes). Other characters ($, commas, ×, letters) stay still.
// The real text is in the HTML for screen readers and search; reduced motion shows it directly.
export function RollingNumber({ value, className = "", duration = 1400, delay = 0 }: { value: string; className?: string; duration?: number; delay?: number }) {
  const el = useRef<HTMLSpanElement>(null);
  const [go, setGo] = useState(false);

  useEffect(() => {
    const node = el.current;
    if (!node) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return setGo(true);
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setGo(true);
          io.disconnect();
        }
      },
      { threshold: 0.3 },
    );
    io.observe(node);
    return () => io.disconnect();
  }, []);

  const chars = [...value];
  const digitCount = chars.filter((c) => /\d/.test(c)).length;
  let d = 0;
  return (
    <span ref={el} className={`tabular inline-flex overflow-hidden leading-none ${className}`}>
      <span className="sr-only">{value}</span>
      <span aria-hidden className="inline-flex">
        {chars.map((c, i) => {
          if (!/\d/.test(c)) return <span key={i}>{c}</span>;
          const n = Number(c);
          const order = d++;
          // Leftmost digits settle last, like the reference; each wheel spins at least one full turn
          const turns = 1 + (digitCount - order > 2 ? 0 : 1);
          const stop = turns * 10 + n;
          return (
            <span key={i} className="relative inline-block h-[1em] overflow-hidden" style={{ width: "0.62em" }}>
              <span
                className="absolute left-0 top-0 flex flex-col"
                style={{
                  transform: `translateY(-${go ? stop : 0}em)`,
                  transition: go ? `transform ${duration + order * 120}ms cubic-bezier(.15,.75,.25,1) ${delay}ms` : "none",
                }}
              >
                {Array.from({ length: stop + 1 }, (_, k) => (
                  <span key={k} className="block h-[1em] text-center">
                    {k % 10}
                  </span>
                ))}
              </span>
            </span>
          );
        })}
      </span>
    </span>
  );
}
