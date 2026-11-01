import Link from "next/link";
import { formatMoney } from "@/lib/api";
import type { Project } from "@/lib/types";
import { CategoryBadge, ProgressBar, UrgencyBadge } from "./ui";

export function ProjectCard({ project: p }: { project: Project }) {
  const pct = (p.raised.amount / p.goal.amount) * 100;
  return (
    <Link
      href={`/projects/${p.id}`}
      className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-5 transition-colors hover:border-primary"
    >
      <div className="flex flex-wrap items-center gap-2">
        <CategoryBadge id={p.categoryId} />
        <UrgencyBadge level={p.urgency} />
      </div>
      <div>
        <h3 className="text-lg font-semibold leading-snug">{p.title}</h3>
        <p className="mt-1 line-clamp-2 text-sm text-muted">{p.summary}</p>
      </div>
      <p className="text-xs text-muted">
        {p.facets.cause} · {p.facets.group} · {p.facets.region}
      </p>
      <div className="mt-auto space-y-2">
        <ProgressBar value={pct} label={`${p.title} funding progress`} />
        <div className="tabular flex justify-between text-sm">
          <span>
            <strong>{formatMoney(p.raised)}</strong> <span className="text-muted">of {formatMoney(p.goal)}</span>
          </span>
          <span className="text-muted">{p.backerCount} backers</span>
        </div>
      </div>
    </Link>
  );
}
