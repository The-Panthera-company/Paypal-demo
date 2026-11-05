"use client";

import Link from "next/link";
import { useState } from "react";
import type { Project } from "@/lib/types";
import { CategoryArt } from "./ui";

type Item = { project: Project; photo: string; raised: string; goal: string; days: number };

// Doria-inspired featured strip: numbered black-and-white panels; the one you point at (or tab to)
// widens into full colour with its story and a Give button. On phones it becomes a swipeable row.
export function FeaturedStrip({ items }: { items: Item[] }) {
  const [active, setActive] = useState(0);

  return (
    <ul className="flex snap-x snap-mandatory gap-1 overflow-x-auto md:h-[480px] md:overflow-visible" aria-label="Featured projects">
      {items.map(({ project: p, photo, raised, goal, days }, i) => {
        const on = i === active;
        const pct = Math.min(100, Math.round((p.raised.amount / p.goal.amount) * 100));
        return (
          <li
            key={p.id}
            onMouseEnter={() => setActive(i)}
            onFocus={() => setActive(i)}
            className={`group relative h-[440px] w-[82%] shrink-0 snap-start overflow-hidden bg-ink text-white transition-[flex-grow] duration-700 ease-out md:h-auto md:w-auto md:shrink ${
              on ? "md:flex-[3.4]" : "md:flex-1"
            }`}
          >
            <div
              className={`absolute inset-0 transition-[filter,transform] duration-700 ${
                on ? "md:scale-100 md:grayscale-0 md:brightness-100" : "md:scale-105 md:grayscale md:brightness-[0.55]"
              }`}
            >
              <CategoryArt id={p.categoryId} seed={p.id} photo={photo} tint={false} label={`Photo for ${p.title}`} />
            </div>
            <div
              className={`absolute inset-0 bg-[linear-gradient(90deg,rgba(11,46,51,0.88),rgba(11,46,51,0.15)_75%)] transition-opacity duration-500 ${on ? "opacity-100" : "opacity-100 md:opacity-0"}`}
              aria-hidden
            />

            <span className="tabular absolute left-5 top-4 font-display text-5xl" aria-hidden>
              {String(i + 1).padStart(2, "0")}
            </span>
            <span
              className={`absolute left-5 top-[84px] w-28 text-[11px] font-bold uppercase leading-4 tracking-[2px] ${on ? "text-accent" : "text-cobalt-green"}`}
              aria-hidden
            >
              {p.categoryId}
            </span>

            <div
              className={`absolute inset-x-0 bottom-0 p-6 transition-all duration-500 md:p-8 ${
                on ? "opacity-100 md:translate-y-0 md:delay-200" : "opacity-100 md:pointer-events-none md:translate-y-4 md:opacity-0"
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
  );
}
