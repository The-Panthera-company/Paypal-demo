import Link from "next/link";
import { FavoritesCount, FavoritesGrid } from "@/components/FavoritesGrid";
import { GivingAssistant } from "@/components/GivingAssistant";
import { PageTitle } from "@/components/PageTitle";
import { ProjectCard } from "@/components/ProjectCard";
import { assignPhotos, EmptyState } from "@/components/ui";
import { getCategories, getFacetOptions, getProjects } from "@/lib/api";
import type { ProjectFilters } from "@/lib/types";

type Params = ProjectFilters & { cards?: string; tab?: string };
const field = "min-h-11 w-full border border-line bg-white px-3 text-sm text-ink";

// Explore: a slim fixed filter menu on the side. Two card arrangements to choose between:
// A1 (default) = a two-column grid of large cards; A2 (`?cards=mosaic`) = a mirrored mosaic where
// cards take different shapes (big, tall, wide) in a repeating symmetrical pattern, the most
// urgent projects in the big tiles. Filters are a plain GET form (works without JavaScript).
export default async function ProjectsPage({ searchParams }: { searchParams: Promise<Params> }) {
  const { cards: rawCards, tab: rawTab, ...filters } = await searchParams;
  const mosaic = rawCards === "mosaic";
  const tab = rawTab === "favorites" ? "favorites" : "all";
  const [projects, all, categories, options] = await Promise.all([getProjects(filters), getProjects(), getCategories(), getFacetOptions()]);
  const active = (Object.keys(filters) as (keyof ProjectFilters)[]).filter((k) => filters[k]);
  const photos = assignPhotos(all);
  const keep = (extra: Record<string, string | undefined>) => {
    const q = new URLSearchParams();
    if (mosaic) q.set("cards", "mosaic");
    for (const [k, v] of Object.entries({ ...filters, ...extra })) if (v) q.set(k, v);
    const s = q.toString();
    return `/projects${s ? `?${s}` : ""}`;
  };
  const labelOf = (k: keyof ProjectFilters, v: string) => (k === "category" ? categories.find((c) => c.id === v)?.name ?? v : v);

  const form = (vertical: boolean) => (
    <form className={vertical ? "space-y-3" : "grid gap-4 sm:grid-cols-2 lg:grid-cols-5"} role="search" action="/projects">
      {mosaic && <input type="hidden" name="cards" value="mosaic" />}
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

  const cols = "sm:grid-cols-2";
  const grid =
    tab === "favorites" ? (
      <FavoritesGrid projects={all} photos={photos} cols={cols} />
    ) : projects.length === 0 ? (
      <EmptyState title="No projects match" body="Try removing a filter, or ask the assistant to suggest something close." action={{ href: keep({ q: undefined, category: undefined, cause: undefined, group: undefined, region: undefined }), label: "Clear filters" }} />
    ) : (
      mosaic ? (
        <Mosaic projects={projects} photos={photos} />
      ) : (
        <div className={`grid gap-6 ${cols}`}>
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} photo={photos[p.id]} />
          ))}
        </div>
      )
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
              <details className="bg-white p-4 shadow-[0_0_30px_rgba(0,0,0,0.05)] lg:[&>summary]:hidden" open>
                <summary className="flex min-h-11 cursor-pointer items-center font-medium text-ink">Filters</summary>
                <h2 className="mb-3 hidden text-lg lg:block">Filters</h2>
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
        </div>
      </section>
      <GivingAssistant projects={all} />
    </>
  );
}

// A2: mirrored mosaic on a 4-column grid. Every 8 cards repeat the pattern
//   [ big  ][tall][tall]      rows 1-2
//   [ wide ][ wide ]          row 3
//   [tall][tall][  big ]      rows 4-5 (mirror of the first block)
// Most urgent projects first, so they land in the big tiles. Phones: one column.
const PATTERN = [
  "sm:col-span-2 sm:row-span-2 lg:col-span-2 lg:row-span-2",
  "lg:col-span-1 lg:row-span-2",
  "lg:col-span-1 lg:row-span-2",
  "sm:col-span-1 lg:col-span-2 lg:row-span-1",
  "sm:col-span-1 lg:col-span-2 lg:row-span-1",
  "lg:col-span-1 lg:row-span-2",
  "lg:col-span-1 lg:row-span-2",
  "sm:col-span-2 sm:row-span-2 lg:col-span-2 lg:row-span-2",
];
const SIZES = ["lg", "sm", "sm", "md", "md", "sm", "sm", "lg"] as const;

function Mosaic({ projects, photos }: { projects: import("@/lib/types").Project[]; photos: Record<string, string> }) {
  const ordered = [...projects].sort((a, b) => b.urgency - a.urgency || a.backerCount - b.backerCount);
  // Leftovers after the last full 8-card block: the first block (big, tall, tall) if 3+ remain,
  // then wide pairs, and a full-width card for an odd one out, so the grid always ends flush.
  const full = Math.floor(ordered.length / PATTERN.length) * PATTERN.length;
  const rest = ordered.length - full;
  const tail: { cls: string; size: (typeof SIZES)[number] }[] = [];
  let left = rest;
  if (left >= 3) {
    for (let k = 0; k < 3; k++) tail.push({ cls: PATTERN[k], size: SIZES[k] });
    left -= 3;
  }
  while (left >= 2) {
    tail.push({ cls: PATTERN[3], size: "md" }, { cls: PATTERN[4], size: "md" });
    left -= 2;
  }
  if (left === 1) tail.push({ cls: "sm:col-span-2 lg:col-span-4 lg:row-span-1", size: "lg" });
  const shape = (i: number) => (i < full ? { cls: PATTERN[i % PATTERN.length], size: SIZES[i % SIZES.length] } : tail[i - full]);
  return (
    <div className="grid auto-rows-[260px] grid-flow-dense gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {ordered.map((p, i) => (
        <div key={p.id} className={shape(i).cls}>
          <ProjectCard project={p} photo={photos[p.id]} fill size={shape(i).size} />
        </div>
      ))}
    </div>
  );
}
