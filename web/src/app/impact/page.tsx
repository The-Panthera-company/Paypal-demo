import Link from "next/link";
import { PageTitle } from "@/components/PageTitle";
import { RollingNumber } from "@/components/RollingNumber";
import { CategoryArt, Eyebrow } from "@/components/ui";
import { formatDate, formatMoney } from "@/lib/api";
import { getGlobePins } from "@/lib/globe";
import { getImpactHub, KIND_LABEL, type Article } from "@/lib/impact";

export const revalidate = 60;

const KINDS = ["all", "release", "round", "spotlight"] as const;

function ArticleCard({ a, big = false }: { a: Article; big?: boolean }) {
  return (
    <article className={`group relative flex flex-col overflow-hidden bg-white shadow-[0_0_30px_rgba(0,0,0,0.05)] ${big ? "lg:flex-row" : ""}`}>
      <div className={`relative overflow-hidden ${big ? "aspect-[4/3] lg:aspect-auto lg:w-3/5" : "aspect-[16/10]"}`}>
        <div className="size-full transition-transform duration-700 group-hover:scale-105">
          <CategoryArt id={a.project?.categoryId ?? "people"} seed={a.project?.id ?? a.slug} label={a.title} />
        </div>
        <span className="absolute left-0 top-4 bg-accent py-1 pl-4 pr-6 text-[11px] font-bold uppercase tracking-[2px] text-ink [clip-path:polygon(0_0,100%_0,88%_100%,0_100%)]">
          {KIND_LABEL[a.kind]}
        </span>
      </div>
      <div className={`flex flex-1 flex-col p-6 ${big ? "lg:p-10" : ""}`}>
        <p className="text-xs uppercase tracking-[2px] text-primary">
          {formatDate(a.date)}
          {a.project && <> · {a.project.facets.region}</>}
        </p>
        <h3 className={`mt-2 ${big ? "text-3xl lg:text-4xl" : "text-xl"} leading-tight`}>
          <Link href={`/impact/${a.slug}`} className="after:absolute after:inset-0 hover:text-primary">
            {a.title}
          </Link>
        </h3>
        <p className={`mt-3 ${big ? "text-lg leading-8" : "text-sm leading-6"}`}>{a.dek}</p>
        <p className="mt-auto pt-4 text-xs font-bold uppercase tracking-[2px] text-primary">Read →</p>
      </div>
    </article>
  );
}

// Impact hub (#7): how the platform's money has helped, as a whole. Articles are drafted from
// verified data (lib/impact.ts), with photo placeholders until projects upload their own.
export default async function ImpactPage({ searchParams }: { searchParams: Promise<{ kind?: string }> }) {
  const { kind: raw } = await searchParams;
  const kind = (KINDS as readonly string[]).includes(raw ?? "") ? (raw as (typeof KINDS)[number]) : "all";
  const [{ articles, stats, places }, globe] = await Promise.all([getImpactHub(), getGlobePins()]);
  const shown = kind === "all" ? articles : articles.filter((a) => a.kind === kind);
  const [lead, ...rest] = shown;
  const m = (a: number) => formatMoney({ amount: a, currency: stats.currency });
  const maxPlace = Math.max(1, ...places.map(([, v]) => v));

  return (
    <>
      <PageTitle title="Impact" crumb="Impact" globe={globe} />

      <section className="bg-ink py-12 text-white">
        <div className="container-k grid grid-cols-2 gap-px bg-white/10 lg:grid-cols-5">
          {(
            [
              [m(stats.released), "released with evidence"],
              [m(stats.raised), "raised by the crowd"],
              [String(stats.backers), "backers"],
              [String(stats.projects), "verified projects"],
              [String(stats.places), "places reached"],
            ] as const
          ).map(([v, l]) => (
            <div key={l} className="bg-ink p-6 text-center">
              <div className="font-display text-3xl text-accent lg:text-4xl">
                <RollingNumber value={v} />
              </div>
              <div className="mt-1 text-sm text-cobalt-green">{l}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="section bg-surface-alt">
        <div className="container-k space-y-10">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div className="max-w-2xl">
              <Eyebrow>News and impact</Eyebrow>
              <h2 className="section-title">Where the money is helping</h2>
              <p className="mt-3">Stories drafted automatically from verified platform data: released milestones, the matching round and projects that need backers. Every number links back to a project.</p>
            </div>
            <nav aria-label="Story type" className="flex flex-wrap gap-2">
              {KINDS.map((k) => (
                <Link
                  key={k}
                  href={k === "all" ? "/impact" : `/impact?kind=${k}`}
                  aria-current={kind === k ? "page" : undefined}
                  className={`flex min-h-11 items-center px-4 text-sm font-medium ${kind === k ? "bg-ink text-white" : "bg-white text-ink ring-1 ring-line hover:ring-primary"}`}
                >
                  {k === "all" ? "All stories" : KIND_LABEL[k]}
                </Link>
              ))}
            </nav>
          </div>

          {lead ? (
            <>
              <ArticleCard a={lead} big />
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {rest.map((a) => (
                  <ArticleCard key={a.slug} a={a} />
                ))}
              </div>
            </>
          ) : (
            <p className="border border-dashed border-line bg-white p-8 text-center">No stories of this kind yet.</p>
          )}

          {places.length > 0 && (
            <section className="bg-white p-6 lg:p-8">
              <h2 className="text-2xl">Where the crowd&apos;s money went</h2>
              <ul className="mt-5 space-y-3">
                {places.map(([place, amount]) => (
                  <li key={place} className="grid grid-cols-[120px_1fr_auto] items-center gap-4 text-sm">
                    <span className="font-medium text-ink">{place}</span>
                    <span className="h-3 bg-line" aria-hidden>
                      <span className="block h-full bg-growth" style={{ width: `${(amount / maxPlace) * 100}%` }} />
                    </span>
                    <span className="tabular text-ink">{m(amount)}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-sm">
                See the photos and receipts in the{" "}
                <Link href="/gallery" className="font-medium text-primary underline">
                  impact gallery
                </Link>
                .
              </p>
            </section>
          )}
        </div>
      </section>
    </>
  );
}
