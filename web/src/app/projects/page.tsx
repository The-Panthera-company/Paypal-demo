import Link from "next/link";
import { formatMoney, getProjects } from "@/lib/api";
import type { ProjectFilters } from "@/lib/types";

// Basic list for Day 1; facet filter controls come in issue #8.
export default async function ProjectsPage({ searchParams }: { searchParams: Promise<ProjectFilters> }) {
  const filters = await searchParams;
  const projects = await getProjects(filters);
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Projects</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map((p) => {
          const pct = Math.min(100, Math.round((p.raised.amount / p.goal.amount) * 100));
          return (
            <Link
              key={p.id}
              href={`/projects/${p.id}`}
              className="space-y-2 rounded-lg border border-black/10 p-5 hover:border-black/30 dark:border-white/10 dark:hover:border-white/30"
            >
              <div className="font-semibold">{p.title}</div>
              <div className="text-xs opacity-70">
                {p.facets.cause} · {p.facets.group} · {p.facets.region}
              </div>
              <div className="h-2 rounded bg-black/10 dark:bg-white/10">
                <div className="h-2 rounded bg-emerald-600" style={{ width: `${pct}%` }} />
              </div>
              <div className="text-sm">
                {formatMoney(p.raised)} of {formatMoney(p.goal)} · {p.backerCount} backers
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
