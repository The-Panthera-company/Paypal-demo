import Link from "next/link";
import { daysLeft, formatMoney } from "@/lib/api";
import type { Project } from "@/lib/types";
import { FavoriteButton } from "./FavoriteButton";
import { CategoryArt } from "./ui";

const catColour: Record<string, string> = {
  health: "bg-cat-health",
  education: "bg-cat-education",
  environment: "bg-cat-environment",
  water: "bg-cat-water",
};

// Photo-first card (Doria-inspired): the photo fills the card, a dark fade carries a few words.
// On hover or keyboard focus the photo zooms into full colour and "Back this project" slides up.
export function ProjectCard({ project: p, photo, fill = false, size = "md" }: { project: Project; photo?: string; fill?: boolean; size?: "sm" | "md" | "lg" }) {
  const pct = Math.min(100, Math.round((p.raised.amount / p.goal.amount) * 100));
  const state = pct >= 100 ? "Funded" : p.backerCount === 0 ? "Just launched" : null;

  return (
    <article className={`group relative overflow-hidden bg-ink text-white ${fill ? "h-full min-h-[320px] sm:min-h-0" : "aspect-[4/5]"}`}>
      <div className="absolute inset-0 saturate-[0.55] transition-[transform,filter] duration-700 ease-out group-focus-within:scale-105 group-focus-within:saturate-100 group-hover:scale-105 group-hover:saturate-100">
        <CategoryArt id={p.categoryId} seed={p.id} photo={photo} tint={false} label={`Photo for ${p.title}`} />
      </div>
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(11,46,51,0)_35%,rgba(11,46,51,0.92)_85%)]" aria-hidden />

      <FavoriteButton id={p.id} title={p.title} className="absolute right-4 top-4 z-10" />
      {state && (
        <span className="absolute left-0 top-5 bg-accent py-1 pl-5 pr-7 text-xs font-bold uppercase tracking-[2px] text-ink [clip-path:polygon(0_0,100%_0,88%_100%,0_100%)]">
          {state}
        </span>
      )}

      <div className="absolute inset-x-0 bottom-0 p-6 transition-transform duration-500 group-hover:-translate-y-1">
        <span className={`inline-block px-3 text-[11px] font-bold uppercase leading-6 tracking-[3px] text-white ${catColour[p.categoryId] ?? "bg-primary"}`}>
          {p.categoryId}
        </span>
        <h3 className={`mt-3 text-white ${size === "lg" ? "text-4xl leading-tight" : size === "sm" ? "text-xl leading-7" : "text-2xl leading-8"}`}>
          <Link href={`/projects/${p.id}`} className="after:absolute after:inset-0 focus-visible:outline-none">
            {p.title}
          </Link>
        </h3>
        {size === "lg" && (
          <p className="mt-2 line-clamp-2 max-w-lg text-white/85">
            {p.summary || `${p.facets.cause.charAt(0).toUpperCase()}${p.facets.cause.slice(1)} for ${p.facets.group.toLowerCase()} in ${p.facets.region}.`}
          </p>
        )}
        <div className="mt-4 flex items-baseline justify-between text-sm">
          <span className="tabular">
            <strong className="text-accent">{formatMoney(p.raised)}</strong> of {formatMoney(p.goal)}
          </span>
          <span className="tabular text-cobalt-green">{daysLeft(p)} days left</span>
        </div>
        <div
          role="progressbar"
          aria-label={`${p.title} funding progress`}
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          className="mt-2 h-1.5 bg-white/20"
        >
          <div className="h-full bg-cobalt-green" style={{ width: `${Math.max(pct, 1)}%` }} />
        </div>
        <p className="grid grid-rows-[0fr] text-xs font-bold uppercase tracking-[2px] text-accent opacity-0 transition-all duration-500 group-focus-within:grid-rows-[1fr] group-focus-within:opacity-100 group-hover:grid-rows-[1fr] group-hover:opacity-100">
          <span className="overflow-hidden pt-3">Back this project →</span>
        </p>
      </div>
      {/* keyboard focus ring drawn inside the card */}
      <span className="pointer-events-none absolute inset-0 hidden ring-4 ring-inset ring-accent group-has-[:focus-visible]:block" aria-hidden />
    </article>
  );
}
