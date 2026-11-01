import Link from "next/link";
import { ProjectCard } from "@/components/ProjectCard";
import { EmptyState } from "@/components/ui";
import { getCategories, getFacetOptions, getProjects } from "@/lib/api";
import type { ProjectFilters } from "@/lib/types";

const selectClass = "min-h-11 rounded-lg border border-line bg-surface px-3 text-sm";

// Filters are a plain GET form: works without JavaScript and keeps the URL shareable.
export default async function ProjectsPage({ searchParams }: { searchParams: Promise<ProjectFilters> }) {
  const filters = await searchParams;
  const [projects, categories, options] = await Promise.all([getProjects(filters), getCategories(), getFacetOptions()]);
  const active = Object.values(filters).some(Boolean);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Projects</h1>
        <p className="text-muted">Every project here is verified. Filter by what you care about.</p>
      </div>

      <form className="grid gap-3 rounded-xl border border-line bg-surface p-4 sm:grid-cols-2 lg:grid-cols-6" role="search">
        <label className="flex flex-col gap-1 text-sm lg:col-span-2">
          Search
          <input name="q" defaultValue={filters.q} placeholder="e.g. library, clean water" className={selectClass} />
        </label>
        {(
          [
            ["category", "Category", categories.map((c) => [c.id, c.name])],
            ["cause", "Cause", options.cause.map((v) => [v, v])],
            ["group", "Who it helps", options.group.map((v) => [v, v])],
            ["region", "Region", options.region.map((v) => [v, v])],
          ] as const
        ).map(([name, label, opts]) => (
          <label key={name} className="flex flex-col gap-1 text-sm">
            {label}
            <select name={name} defaultValue={filters[name] ?? ""} className={selectClass}>
              <option value="">All</option>
              {opts.map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
            </select>
          </label>
        ))}
        <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-6">
          <button className="min-h-11 rounded-lg bg-primary px-5 text-sm font-medium text-white hover:bg-primary-hover">
            Apply filters
          </button>
          {active && (
            <Link href="/projects" className="flex min-h-11 items-center rounded-lg px-4 text-sm text-muted hover:bg-primary-soft">
              Clear
            </Link>
          )}
          <span className="tabular ml-auto text-sm text-muted" aria-live="polite">
            {projects.length} {projects.length === 1 ? "project" : "projects"}
          </span>
        </div>
      </form>

      {projects.length === 0 ? (
        <EmptyState
          title="No projects match these filters"
          body="Try removing a filter, or ask the assistant to suggest something close."
          action={{ href: "/projects", label: "Clear all filters" }}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      )}
    </div>
  );
}
