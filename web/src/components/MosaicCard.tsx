import Link from "next/link";
import { daysLeft, formatMoney } from "@/lib/api";
import type { Project } from "@/lib/types";
import { FavoriteButton } from "./FavoriteButton";
import { CategoryArt } from "./ui";

// Explore mosaic tile: the photo first. At rest only the title, a thin progress line on the bottom
// edge and the heart; hovering or focusing the tile slides up the details (category, place,
// summary, money, backers, days left). Touch screens: the first tap focuses and shows the details.
export function MosaicCard({ project: p, photo, size }: { project: Project; photo?: string; size: "lg" | "md" | "sm" }) {
  const pct = Math.min(100, Math.round((p.raised.amount / p.goal.amount) * 100));
  const summary = p.summary || `${p.facets.cause.charAt(0).toUpperCase()}${p.facets.cause.slice(1)} for ${p.facets.group.toLowerCase()} in ${p.facets.region}.`;
  return (
    <article className="group relative h-full min-h-[340px] overflow-hidden bg-ink text-white sm:min-h-0">
      <div className="absolute inset-0 transition-transform duration-700 ease-out group-focus-within:scale-105 group-hover:scale-105">
        <CategoryArt id={p.categoryId} seed={p.id} photo={photo} tint={false} label={`Photo for ${p.title}`} />
      </div>
      {/* Light fade at rest, deepens with the details */}
      <div className="absolute inset-0 bg-[linear-gradient(180deg,transparent_55%,rgba(11,46,51,0.75))] transition-opacity duration-500 group-focus-within:opacity-0 group-hover:opacity-0" aria-hidden />
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(11,46,51,0.25),rgba(11,46,51,0.94)_65%)] opacity-0 transition-opacity duration-500 group-focus-within:opacity-100 group-hover:opacity-100" aria-hidden />

      <FavoriteButton id={p.id} title={p.title} className="absolute right-4 top-4 z-10" />

      <div className="absolute inset-x-0 bottom-0 p-5 lg:p-6">
        {/* Details: hidden until hover/focus */}
        <div className="grid grid-rows-[0fr] opacity-0 transition-all duration-500 group-focus-within:grid-rows-[1fr] group-focus-within:opacity-100 group-hover:grid-rows-[1fr] group-hover:opacity-100">
          <div className="overflow-hidden">
            <p className="text-[11px] font-bold uppercase tracking-[2px] text-accent">
              {p.categoryId} · {p.facets.region}
            </p>
          </div>
        </div>
        <h3 className={`mt-1 text-white [text-shadow:0_1px_12px_rgba(0,0,0,0.45)] ${size === "lg" ? "text-3xl leading-tight lg:text-4xl" : size === "md" ? "text-2xl leading-8" : "text-xl leading-7"}`}>
          <Link href={`/projects/${p.id}`} className="after:absolute after:inset-0 focus-visible:outline-none">
            {p.title}
          </Link>
        </h3>
        <div className="grid grid-rows-[0fr] opacity-0 transition-all duration-500 group-focus-within:grid-rows-[1fr] group-focus-within:opacity-100 group-hover:grid-rows-[1fr] group-hover:opacity-100">
          <div className="overflow-hidden">
            <p className={`mt-2 text-sm leading-6 text-white/90 ${size === "lg" ? "line-clamp-3" : "line-clamp-2"}`}>{summary}</p>
            <div className="mt-3 flex items-baseline justify-between gap-3 text-sm">
              <span className="tabular">
                <strong className="text-accent">{formatMoney(p.raised)}</strong> of {formatMoney(p.goal)}
              </span>
              <span className="tabular">{pct}%</span>
            </div>
            <div className="mt-2 h-1.5 bg-white/20" aria-hidden>
              <div className="h-full bg-cobalt-green" style={{ width: `${Math.max(pct, 1)}%` }} />
            </div>
            <p className="mt-2 flex flex-wrap justify-between gap-2 text-xs text-cobalt-green">
              <span>{p.backerCount} backers</span>
              <span>{daysLeft(p)} days left</span>
            </p>
            <p className="mt-3 text-xs font-bold uppercase tracking-[2px] text-accent">View project →</p>
          </div>
        </div>
      </div>

      {/* Thin progress line on the bottom edge, always visible */}
      <div
        className="absolute inset-x-0 bottom-0 h-1 bg-white/20 transition-opacity group-focus-within:opacity-0 group-hover:opacity-0"
        role="progressbar"
        aria-label={`${p.title} funding progress`}
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="h-full bg-accent" style={{ width: `${Math.max(pct, 1)}%` }} />
      </div>
      <span className="pointer-events-none absolute inset-0 hidden ring-4 ring-inset ring-accent group-has-[:focus-visible]:block" aria-hidden />
    </article>
  );
}
