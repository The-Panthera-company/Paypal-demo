import { notFound } from "next/navigation";
import { PageTitle } from "@/components/PageTitle";
import { CategoryArt, ProgressBar, StatBox } from "@/components/ui";
import Link from "next/link";
import { DonatePanel } from "@/components/DonatePanel";
import { ProjectCard } from "@/components/ProjectCard";
import { daysLeft, formatDate, formatMoney, getImpactUpdates, getProject, getSimilarProjects } from "@/lib/api";

// Krowd single-project layout, with the PayPal donate panel (#14).
export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const p = await getProject(id);
  if (!p) notFound();
  const pct = Math.round((p.raised.amount / p.goal.amount) * 100);
  const [updates, similar] = await Promise.all([getImpactUpdates(p.id), getSimilarProjects(p)]);

  return (
    <>
      <PageTitle title="Project details" crumb={p.title} />
      <section className="bg-surface-alt pb-24 pt-12 lg:pb-32 lg:pt-[120px]">
        <div className="container-k grid gap-10 lg:grid-cols-2">
          <div className="aspect-[4/3]">
            <CategoryArt id={p.categoryId} seed={p.id} label={`Photo for ${p.title}`} />
          </div>
          <div>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <span className="tag">{p.categoryId}</span>
              <span className="text-sm text-ink">{p.facets.region}</span>
            </div>
            <h1 className="mb-2 text-4xl">{p.title}</h1>
            <p className="mb-6">
              {p.facilitator ? (
                <>
                  Facilitated by <span className="font-medium text-ink">{p.facilitator}</span> ·{" "}
                </>
              ) : null}
              {p.status === "frozen" ? "Matching paused for review" : "Verified"}
            </p>
            <div className="mb-8 grid grid-cols-3 gap-3 sm:gap-[30px]">
              <StatBox value={formatMoney(p.raised)} label="Raised" />
              <StatBox value={String(p.backerCount)} label="Backers" />
              <StatBox value={String(daysLeft(p))} label="Days left" />
            </div>
            <div className="mb-2 flex justify-between text-sm font-medium text-ink">
              <span>Raised</span>
              <span className="tabular">{pct}%</span>
            </div>
            <ProgressBar value={pct} label="Funding progress" />
            <p className="tabular mb-8 mt-4 font-bold text-ink">
              Goal: <span className="text-brand">{formatMoney(p.goal)}</span>
            </p>
            <h2 className="mb-3 text-2xl">Back this project</h2>
            <DonatePanel projectId={p.id} projectTitle={p.title} />
            <p className="mt-4 text-sm">Your name stays private unless you opt in to the leaderboard.</p>
          </div>
        </div>
      </section>

      <section className="pb-16 lg:pb-[120px]">
        <div className="container-k">
          <div className="-mt-[72px] flex flex-wrap bg-brand" role="tablist" aria-label="Project sections">
            {["Story", "Updates", "Documents"].map((t, i) => (
              <span
                key={t}
                role="tab"
                aria-selected={i === 0}
                className={`px-8 py-5 text-xl font-medium ${i === 0 ? "bg-white text-ink" : "text-white"}`}
              >
                {t}
              </span>
            ))}
          </div>
          <div className="max-w-[760px] pt-10" role="tabpanel">
            <h2 className="mb-4 text-3xl">About this project</h2>
            <p className="text-lg leading-9">{p.summary}</p>
            <p className="mt-6 text-lg leading-9">
              Matching money for this project is released in tranches: each milestone needs receipts and photos that pass
              our checks before the next payment is sent.
            </p>

            <h2 className="mb-6 mt-12 text-3xl">Impact updates</h2>
            {updates.length === 0 ? (
              <p className="border border-dashed border-line p-6">No milestone released yet. Updates with receipts and photos appear here.</p>
            ) : (
              <ol className="space-y-6 border-l-2 border-line pl-6">
                {updates.map((u) => (
                  <li key={u.id} className="relative">
                    <span className="absolute -left-[31px] top-1.5 size-3 bg-growth" aria-hidden />
                    <p className="text-sm">
                      {formatDate(u.date)} · {u.kind === "receipt" ? "Receipt" : "Photo"}
                      {u.tranche && <> · {formatMoney(u.tranche)} released</>}
                    </p>
                    <h3 className="text-xl">{u.title}</h3>
                    <p>{u.caption}</p>
                  </li>
                ))}
              </ol>
            )}

            <p className="mt-12 text-sm">
              Something wrong with this project?{" "}
              <Link href={`/report?project=${p.id}`} className="font-medium text-brand underline">
                Report it
              </Link>{" "}
              and an admin will review it.
            </p>
          </div>
        </div>
      </section>

      {similar.length > 0 && (
        <section className="bg-surface-alt section">
          <div className="container-k">
            <h2 className="section-title mb-8">Similar projects</h2>
            <div className="grid gap-[30px] sm:grid-cols-2 lg:grid-cols-3">
              {similar.map((x) => (
                <ProjectCard key={x.id} project={x} />
              ))}
            </div>
          </div>
        </section>
      )}

      <div className="h-20 lg:hidden" aria-hidden />
      {/* Sticky back bar on phones */}
      <div className="fixed inset-x-0 bottom-0 z-20 flex items-center gap-4 border-t border-line bg-white p-3 lg:hidden">
        <div className="flex-1 text-sm">
          <div className="tabular font-bold text-ink">{formatMoney(p.raised)}</div>
          <div>{pct}% of {formatMoney(p.goal)}</div>
        </div>
        <a href="#donate" className="btn !min-h-12 !px-6">
          Back this
        </a>
      </div>
    </>
  );
}
