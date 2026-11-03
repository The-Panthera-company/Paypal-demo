import Link from "next/link";
import { daysLeft, formatMoney } from "@/lib/api";
import type { Project } from "@/lib/types";
import { CategoryArt, ProgressBar } from "./ui";

// Krowd standard project card: image on top (zooms on hover), white content box with a
// border that turns into a soft shadow on hover. Every number comes from data.
export function ProjectCard({ project: p }: { project: Project }) {
  const pct = Math.round((p.raised.amount / p.goal.amount) * 100);
  const days = daysLeft(p);
  const state = pct >= 100 ? "Funded" : p.backerCount === 0 ? "Just launched" : null;

  return (
    <article className="group relative flex flex-col bg-white transition-shadow duration-300 hover:shadow-[0_15px_35px_rgba(27,31,46,0.08)]">
      <div className="relative aspect-[4/3] overflow-hidden">
        <div className="size-full transition-transform duration-300 group-hover:scale-110">
          <CategoryArt id={p.categoryId} seed={p.id} label={`Photo for ${p.title}`} />
        </div>
        {state && (
          <span className="absolute left-5 top-5 bg-accent px-3 text-xs font-bold uppercase leading-7 tracking-[2px] text-ink">{state}</span>
        )}
      </div>
      <div className="flex flex-1 flex-col border border-t-0 border-line px-6 pb-8 pt-8 transition-colors group-hover:border-transparent lg:px-[50px] lg:pt-10">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <span className="tag">{p.categoryId}</span>
          <span className="flex items-center gap-1.5 text-xs font-medium text-ink">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5l3 2" />
            </svg>
            {days} days left
          </span>
        </div>
        <h3 className="mb-2 text-2xl leading-9 transition-colors">
          <Link href={`/projects/${p.id}`} className="after:absolute after:inset-0 group-hover:text-brand">
            {p.title}
          </Link>
        </h3>
        <p className="mb-5 text-sm">
          {p.facets.cause} · {p.facets.group} · {p.facets.region}
        </p>
        <div className="mt-auto">
          <div className="mb-2 flex justify-between text-sm font-medium text-ink">
            <span>Raised</span>
            <span className="tabular">{pct}%</span>
          </div>
          <ProgressBar value={pct} label={`${p.title} funding progress`} />
          <p className="tabular mt-4 font-bold text-ink">
            {formatMoney(p.raised)} <span className="font-normal text-text">of</span>{" "}
            <span className="text-brand">{formatMoney(p.goal)}</span>
          </p>
          <p className="mt-1 text-sm">{p.backerCount} backers</p>
        </div>
      </div>
    </article>
  );
}
