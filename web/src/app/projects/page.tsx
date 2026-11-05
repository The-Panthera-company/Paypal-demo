import Link from "next/link";
import { FavoritesCount, FavoritesGrid } from "@/components/FavoritesGrid";
import { GivingAssistant } from "@/components/GivingAssistant";
import { PageTitle } from "@/components/PageTitle";
import { ProjectCard } from "@/components/ProjectCard";
import { assignPhotos, EmptyState } from "@/components/ui";
import { getCategories, getFacetOptions, getProjects } from "@/lib/api";
import type { ProjectFilters } from "@/lib/types";

type Params = ProjectFilters & { layout?: string; tab?: string };
const field = "min-h-12 w-full border border-line bg-white px-4 text-ink";

// Explore. Two layouts to choose between (owner A/B test): A = fixed filter menu on the side and a
// two-column grid; B = filters hidden behind a button at the top and a three-column grid.
// `?layout=b` shows B. Filters are a plain GET form (works without JavaScript, shareable URL).
export default async function ProjectsPage({ searchParams }: { searchParams: Promise<Params> }) {
  const { layout: rawLayout, tab: rawTab, ...filters } = await searchParams;
  const layout = rawLayout === "b" ? "b" : "a";
  const tab = rawTab === "favorites" ? "favorites" : "all";
  const [projects, all, categories, options] = await Promise.all([getProjects(filters), getProjects(), getCategories(), getFacetOptions()]);
  const active = (Object.keys(filters) as (keyof ProjectFilters)[]).filter((k) => filters[k]);
  const photos = assignPhotos(all);
  const keep = (extra: Record<string, string | undefined>) => {
    const q = new URLSearchParams();
    if (layout === "b") q.set("layout", "b");
    for (const [k, v] of Object.entries({ ...filters, ...extra })) if (v) q.set(k, v);
    const s = q.toString();
    return `/projects${s ? `?${s}` : ""}`;
  };
  const labelOf = (k: keyof ProjectFilters, v: string) => (k === "category" ? categories.find((c) => c.id === v)?.name ?? v : v);

  const form = (vertical: boolean) => (
    <form className={vertical ? "space-y-4" : "grid gap-4 sm:grid-cols-2 lg:grid-cols-5"} role="search" action="/projects">
      {layout === "b" && <input type="hidden" name="layout" value="b" />}
      <label className={`flex flex-col gap-1 text-sm text-ink ${vertical ? "" : "lg:col-span-1"}`}>
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
      <div className={`flex flex-wrap items-center gap-4 ${vertical ? "" : "sm:col-span-2 lg:col-span-5"}`}>
        <button className={`btn btn-2 ${vertical ? "w-full" : ""}`}>Apply filters</button>
        {active.length > 0 && (
          <Link href={keep({ q: undefined, category: undefined, cause: undefined, group: undefined, region: undefined })} className="text-sm font-medium text-brand underline-offset-4 hover:underline">
            Clear all
          </Link>
        )}
      </div>
    </form>
  );

  const tabs = (
    <nav aria-label="Projects or favourites" className="flex gap-1 bg-white p-1 shadow-[0_0_30px_rgba(0,0,0,0.05)]">
      {(
        [
          ["all", "All projects", keep({})],
          ["favorites", "Favourites", `${keep({})}${keep({}).includes("?") ? "&" : "?"}tab=favorites`],
        ] as const
      ).map(([id, label, href]) => (
        <Link
          key={id}
          href={href}
          aria-current={tab === id ? "page" : undefined}
          className={`flex min-h-11 items-center px-5 font-medium ${tab === id ? "bg-ink text-white" : "text-ink hover:bg-surface-alt"}`}
        >
          {label}
          {id === "favorites" ? <FavoritesCount /> : <span className="tabular ml-1.5 text-sm opacity-70">{projects.length}</span>}
        </Link>
      ))}
    </nav>
  );

  const chips = active.length > 0 && (
    <ul className="flex flex-wrap gap-2" aria-label="Active filters">
      {active.map((k) => (
        <li key={k}>
          <Link href={keep({ [k]: undefined })} className="flex min-h-9 items-center gap-2 border border-primary bg-white px-3 text-sm text-primary hover:bg-primary hover:text-white">
            {labelOf(k, filters[k]!)} <span aria-hidden>×</span>
            <span className="sr-only">Remove this filter</span>
          </Link>
        </li>
      ))}
    </ul>
  );

  const cols = layout === "a" ? "sm:grid-cols-2" : "sm:grid-cols-2 lg:grid-cols-3";
  const grid =
    tab === "favorites" ? (
      <FavoritesGrid projects={all} photos={photos} cols={cols} />
    ) : projects.length === 0 ? (
      <EmptyState title="No projects match" body="Try removing a filter, or ask the assistant to suggest something close." action={{ href: keep({ q: undefined, category: undefined, cause: undefined, group: undefined, region: undefined }), label: "Clear filters" }} />
    ) : (
      <div className={`grid gap-[30px] ${cols}`}>
        {projects.map((p) => (
          <ProjectCard key={p.id} project={p} photo={photos[p.id]} />
        ))}
      </div>
    );

  const categoryBanner = filters.category && tab === "all" && (
    <div className="flex flex-wrap items-center justify-between gap-4 bg-ink p-5 text-white">
      <p>Can&apos;t choose? Give to every {labelOf("category", filters.category)} project at once and see where it goes before you pay.</p>
      <Link href={`/give/${filters.category}`} className="btn">
        Give to all {labelOf("category", filters.category)}
      </Link>
    </div>
  );

  return (
    <>
      <PageTitle title="Explore projects" crumb="Explore" />
      <section className="relative pb-16 lg:pb-[120px]">
        <div className="absolute inset-x-0 top-0 h-[600px] bg-surface-alt" aria-hidden />
        <div className="container-k relative pt-12 lg:pt-16">
          {layout === "a" ? (
            // Option A: fixed filter menu on the side, two-column grid
            <div className="grid gap-8 lg:grid-cols-[290px_1fr]">
              <aside className="lg:sticky lg:top-32 lg:self-start">
                <details className="bg-white p-5 shadow-[0_0_30px_rgba(0,0,0,0.05)] lg:[&>summary]:hidden" open>
                  <summary className="flex min-h-11 cursor-pointer items-center font-medium text-ink">Filters</summary>
                  <h2 className="mb-4 hidden text-xl lg:block">Filters</h2>
                  {form(true)}
                </details>
              </aside>
              <div className="space-y-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  {tabs}
                  {chips}
                </div>
                {categoryBanner}
                {grid}
              </div>
            </div>
          ) : (
            // Option B: a clean top bar; filters toggle out from a button
            <div className="space-y-6">
              <div className="relative flex flex-wrap items-center justify-between gap-4">
                {tabs}
                <details className="group">
                  <summary className="flex min-h-12 cursor-pointer list-none items-center gap-2 bg-ink px-5 font-medium text-white hover:bg-primary [&::-webkit-details-marker]:hidden">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
                      <path d="M4 6h16M7 12h10M10 18h4" />
                    </svg>
                    <span className="group-open:hidden">Filters{active.length ? ` (${active.length})` : ""}</span>
                    <span className="hidden group-open:inline">Hide filters</span>
                  </summary>
                  <div className="absolute inset-x-0 top-full z-20 mt-3 animate-[showcase-in_.3s_ease-out] bg-white p-5 shadow-[0_20px_40px_rgba(11,46,51,0.18)]">{form(false)}</div>
                </details>
              </div>
              {chips}
              {categoryBanner}
              {grid}
            </div>
          )}
        </div>
      </section>
      <GivingAssistant projects={all} />
    </>
  );
}
