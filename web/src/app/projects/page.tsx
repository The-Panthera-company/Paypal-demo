import Link from "next/link";
import { GivingAssistant } from "@/components/GivingAssistant";
import { PageTitle } from "@/components/PageTitle";
import { ProjectCard } from "@/components/ProjectCard";
import { assignPhotos, EmptyState } from "@/components/ui";
import { getCategories, getFacetOptions, getProjects } from "@/lib/api";
import type { ProjectFilters } from "@/lib/types";

const field = "min-h-12 border border-line bg-white px-4 text-ink";

// Filters are a plain GET form: works without JavaScript and keeps the URL shareable.
export default async function ProjectsPage({ searchParams }: { searchParams: Promise<ProjectFilters> }) {
  const filters = await searchParams;
  const [projects, categories, options] = await Promise.all([getProjects(filters), getCategories(), getFacetOptions()]);
  const active = Object.values(filters).some(Boolean);
  const photos = assignPhotos(projects);

  return (
    <>
      <PageTitle title="Explore projects" crumb="Explore" />
      <section className="relative pb-16 lg:pb-[120px]">
        <div className="absolute inset-x-0 top-0 h-[600px] bg-surface-alt" aria-hidden />
        <div className="container-k relative pt-12 lg:pt-16">
          <details className="mb-8 bg-white shadow-[0_0_30px_rgba(0,0,0,0.05)] lg:[&>summary]:hidden" open>
            <summary className="flex min-h-12 cursor-pointer items-center px-5 font-medium text-ink">Filters</summary>
            <form className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-6" role="search">
              <label className="flex flex-col gap-1 text-sm text-ink lg:col-span-2">
                Search
                <input name="q" defaultValue={filters.q} placeholder="e.g. library, clean water" className={field} />
              </label>
              {(
                [
                  ["category", "Category", categories.map((c) => [c.id, c.name])],
                  ["cause", "Cause", options.cause.map((v) => [v, v])],
                  ["group", "Who it helps", options.group.map((v) => [v, v])],
                  ["region", "Region", options.region.map((v) => [v, v])],
                ] as const
              ).map(([name, label, opts]) => (
                <label key={name} className="flex flex-col gap-1 text-sm text-ink">
                  {label}
                  <select name={name} defaultValue={filters[name] ?? ""} className={field}>
                    <option value="">All</option>
                    {opts.map(([value, text]) => (
                      <option key={value} value={value}>
                        {text}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              <div className="flex flex-wrap items-center gap-4 sm:col-span-2 lg:col-span-6">
                <button className="btn btn-2">Apply filters</button>
                {active && (
                  <Link href="/projects" className="text-sm font-medium text-brand underline-offset-4 hover:underline">
                    Clear all
                  </Link>
                )}
                <span className="tabular ml-auto text-sm text-ink" aria-live="polite">
                  {projects.length} {projects.length === 1 ? "project" : "projects"}
                </span>
              </div>
            </form>
          </details>

          {filters.category && (
            <div className="mb-8 flex flex-wrap items-center justify-between gap-4 bg-ink p-5 text-white">
              <p>Can&apos;t choose? Give to every {filters.category} project at once and see where it goes before you pay.</p>
              <Link href={`/give/${filters.category}`} className="btn">
                Give to all {filters.category}
              </Link>
            </div>
          )}

          {projects.length === 0 ? (
            <EmptyState
              title="No projects match"
              body="Try removing a filter, or ask the assistant to suggest something close."
              action={{ href: "/projects", label: "Clear filters" }}
            />
          ) : (
            <div className="grid gap-[30px] sm:grid-cols-2 lg:grid-cols-3">
              {projects.map((p) => (
                <ProjectCard key={p.id} project={p} photo={photos[p.id]} />
              ))}
            </div>
          )}
        </div>
      </section>
      <GivingAssistant projects={await getProjects()} />
    </>
  );
}
