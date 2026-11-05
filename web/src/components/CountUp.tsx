"use client";

import { useEffect, useRef, useState } from "react";

// A number that counts up from 0 the first time it scrolls into view (ease-out, ~1.6 s).
// The server renders the final value, so no-JS readers, search engines and screen readers get the
// real number; reduced-motion users see it without animation.
export function CountUp({ value, format = "number", currency = "USD", duration = 1600 }: { value: number; format?: "number" | "money"; currency?: string; duration?: number }) {
  const el = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(value);
  const done = useRef(false);

  useEffect(() => {
    const node = el.current;
    if (!node || done.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // Only animate numbers that start below the fold (otherwise a visible number would flash to 0)
    if (node.getBoundingClientRect().top < window.innerHeight) return;
    setShown(0);
    let raf = 0;
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting || done.current) return;
        done.current = true;
        io.disconnect();
        const start = performance.now();
        const tick = (t: number) => {
          const p = Math.min(1, (t - start) / duration);
          setShown(Math.round(value * (1 - Math.pow(1 - p, 3))));
          if (p < 1) raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      },
      { threshold: 0.4 },
    );
    io.observe(node);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [value, duration]);

  const text =
    format === "money"
      ? new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(shown / 100)
      : shown.toLocaleString();
  const final =
    format === "money"
      ? new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(value / 100)
      : value.toLocaleString();

  return (
    <span ref={el} className="tabular">
      <span aria-hidden>{text}</span>
      <span className="sr-only">{final}</span>
    </span>
  );
}
