import Link from "next/link";
import { FavoritesCount, FavoritesGrid } from "@/components/FavoritesGrid";
import { FurthestFive } from "@/components/FurthestFive";
import { RecommendedGrid } from "@/components/RecommendedGrid";
import { GivingAssistant } from "@/components/GivingAssistant";
import { PageTitle } from "@/components/PageTitle";
import { ProjectMosaic } from "@/components/ProjectMosaic";
import { assignPhotos, EmptyState } from "@/components/ui";
import { getCategories, getFacetOptions, getProjects } from "@/lib/api";
import type { ProjectFilters } from "@/lib/types";

type Params = ProjectFilters & { tab?: string };
const field = "min-h-11 w-full border border-line bg-white px-3 text-sm text-ink";

// Explore: a slim fixed filter menu on the side and the project mosaic (photos first, details on
// hover). Filters are a plain GET form (works without JavaScript, shareable URL).
export default async function ProjectsPage({ searchParams }: { searchParams: Promise<Params> }) {
  const { tab: rawTab, ...filters } = await searchParams;
  const tab = rawTab === "favorites" ? "favorites" : rawTab === "ai" ? "ai" : "all";
  const [projects, all, categories, options] = await Promise.all([getProjects(filters), getProjects(), getCategories(), getFacetOptions()]);
  const active = (Object.keys(filters) as (keyof ProjectFilters)[]).filter((k) => filters[k]);
  const photos = assignPhotos(all);
  const keep = (extra: Record<string, string | undefined>) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries({ ...filters, ...extra })) if (v) q.set(k, v);
    const s = q.toString();
    return `/projects${s ? `?${s}` : ""}`;
  };
  const labelOf = (k: keyof ProjectFilters, v: string) => (k === "category" ? categories.find((c) => c.id === v)?.name ?? v : v);

  const form = (vertical: boolean) => (
    <form className={vertical ? "space-y-3" : "grid gap-4 sm:grid-cols-2 lg:grid-cols-5"} role="search" action="/projects">
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
        <button className={`btn btn-2 ${vertical ? "w-full !px-4" : ""}`}>{vertical ? "Apply" : "Apply filters"}</button>
        {active.length > 0 && (
          <Link href={keep({ q: undefined, category: undefined, cause: undefined, group: undefined, region: undefined })} className="text-sm font-medium text-brand underline-offset-4 hover:underline">
            Clear all
          </Link>
        )}
      </div>
    </form>
  );

  const tabs = (
    <nav aria-label="Projects or favourites" className="flex flex-wrap gap-1 bg-white p-1 shadow-[0_0_30px_rgba(0,0,0,0.05)]">
      {(
        [
          ["all", "All projects", keep({})],
          ["ai", "AI recommended", `${keep({})}${keep({}).includes("?") ? "&" : "?"}tab=ai`],
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
          {id === "favorites" ? <FavoritesCount /> : id === "all" ? <span className="tabular ml-1.5 text-sm opacity-70">{projects.length}</span> : <span className="ml-1.5" aria-hidden>✦</span>}
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

  const grid =
    tab === "ai" ? (
      <RecommendedGrid projects={all} photos={photos} />
    ) : tab === "favorites" ? (
      <FavoritesGrid projects={all} photos={photos} />
    ) : projects.length === 0 ? (
      <EmptyState title="No projects match" body="Try removing a filter, or ask the assistant to suggest something close." action={{ href: keep({ q: undefined, category: undefined, cause: undefined, group: undefined, region: undefined }), label: "Clear filters" }} />
    ) : (
      <ProjectMosaic projects={projects} photos={photos} />
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
        <div className="container-k relative pt-12 lg:!max-w-[1360px] lg:pt-16">
          <div className="grid gap-8 lg:grid-cols-[230px_1fr]">
            <aside className="lg:sticky lg:top-32 lg:self-start">
              {/* Phones and tablets: filters folded away (open when any is set); desktop: always shown */}
              <details className="bg-white p-4 shadow-[0_0_30px_rgba(0,0,0,0.05)] lg:hidden" open={active.length > 0}>
                <summary className="flex min-h-11 cursor-pointer items-center justify-between font-medium text-ink">
                  Filters{active.length > 0 && <span className="tabular bg-ink px-2 text-xs leading-6 text-white">{active.length}</span>}
                </summary>
                <div className="mt-3">{form(true)}</div>
              </details>
              <div className="hidden bg-white p-4 shadow-[0_0_30px_rgba(0,0,0,0.05)] lg:block">
                <h2 className="mb-3 text-lg">Filters</h2>
                {form(true)}
              </div>
            </aside>
            <div className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                {tabs}
                {chips}
              </div>
              {categoryBanner}
              {tab === "all" && <FurthestFive projectIds={projects.map((p) => p.id)} />}
              {grid}
            </div>
          </div>
        </div>
      </section>
      <GivingAssistant projects={all} />
    </>
  );
}

