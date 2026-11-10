import Link from "next/link";
import { notFound } from "next/navigation";
import { PageTitle } from "@/components/PageTitle";
import { DEMO_PHOTOS, CategoryArt } from "@/components/ui";
import { formatDate, formatMoney } from "@/lib/api";
import { getImpactHub, KIND_LABEL } from "@/lib/impact";

export const revalidate = 60;

export default async function ArticlePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const { articles } = await getImpactHub();
  const a = articles.find((x) => x.slug === slug);
  if (!a) notFound();
  const more = articles.filter((x) => x.slug !== slug).slice(0, 3);

  return (
    <>
      <PageTitle title="Impact story" crumb={KIND_LABEL[a.kind]} />
      <article className="section">
        <div className="container-k mx-auto max-w-3xl">
          <p className="text-sm uppercase tracking-[2px] text-primary">
            {KIND_LABEL[a.kind]} · {formatDate(a.date)}
            {a.project && <> · {a.project.facets.region}</>}
          </p>
          <h1 className="mt-3 text-4xl leading-tight lg:text-5xl">{a.title}</h1>
          <p className="mt-4 text-xl leading-9 text-ink">{a.dek}</p>
          <div className="my-8 aspect-[16/9]">
            <CategoryArt id={a.project?.categoryId ?? "people"} photo={DEMO_PHOTOS[a.project?.title ?? ""]} seed={a.project?.id ?? a.slug} label="Photo placeholder until the project uploads its own" />
          </div>
          <div className="space-y-5 text-lg leading-9">
            {a.body.map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
          {a.amount && (
            <p className="mt-8 border-l-4 border-growth bg-surface-alt p-4 text-ink">
              <strong className="tabular">{formatMoney(a.amount)}</strong> released after {a.evidence > 1 ? "receipts and photos" : "evidence"} passed the checks.
            </p>
          )}
          <p className="mt-8 border border-line p-4 text-sm">
            Drafted automatically from verified platform data (milestones, evidence checks, matching results). Photos are placeholders until projects upload their own.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            {a.project ? (
              <Link href={`/projects/${a.project.id}`} className="btn">
                See {a.project.title}
              </Link>
            ) : (
              <Link href="/leaderboard?tab=projects" className="btn">
                See the leaderboard
              </Link>
            )}
            <Link href="/impact" className="btn btn-2">
              All stories
            </Link>
          </div>
        </div>
      </article>
      {more.length > 0 && (
        <section className="section bg-surface-alt">
          <div className="container-k">
            <h2 className="mb-6 text-2xl">More stories</h2>
            <ul className="grid gap-6 sm:grid-cols-3">
              {more.map((x) => (
                <li key={x.slug} className="bg-white p-5">
                  <p className="text-xs uppercase tracking-[2px] text-primary">{KIND_LABEL[x.kind]}</p>
                  <Link href={`/impact/${x.slug}`} className="mt-2 block font-display text-lg leading-6 hover:text-primary">
                    {x.title}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </>
  );
}
