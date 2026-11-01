import { notFound } from "next/navigation";
import { PageTitle } from "@/components/PageTitle";
import { CategoryArt, ProgressBar, StatBox } from "@/components/ui";
import { daysLeft, formatMoney, getProject } from "@/lib/api";

// Krowd single-project layout. Story/Updates tabs content: issue #11; PayPal button: #14.
export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const p = await getProject(id);
  if (!p) notFound();
  const pct = Math.round((p.raised.amount / p.goal.amount) * 100);

  return (
    <>
      <PageTitle title="Project details" crumb={p.title} />
      <section className="bg-surface-alt pb-24 pt-12 lg:pb-32 lg:pt-[120px]">
        <div className="container-k grid gap-10 lg:grid-cols-2">
          <div className="aspect-[4/3]">
            <CategoryArt id={p.categoryId} />
          </div>
          <div>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <span className="tag">{p.categoryId}</span>
              <span className="text-sm text-ink">{p.facets.region}</span>
            </div>
            <h1 className="mb-2 text-4xl">{p.title}</h1>
            <p className="mb-6">
              Facilitated by <span className="font-medium text-ink">{p.facilitator}</span> · Verified
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
            <button disabled className="btn w-full sm:w-auto" title="PayPal button arrives in issue #14">
              Back this project
            </button>
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
          </div>
        </div>
      </section>

      <div className="h-20 lg:hidden" aria-hidden />
      {/* Sticky back bar on phones */}
      <div className="fixed inset-x-0 bottom-0 z-20 flex items-center gap-4 border-t border-line bg-white p-3 lg:hidden">
        <div className="flex-1 text-sm">
          <div className="tabular font-bold text-ink">{formatMoney(p.raised)}</div>
          <div>{pct}% of {formatMoney(p.goal)}</div>
        </div>
        <button disabled className="btn !min-h-12 !px-6">
          Back this
        </button>
      </div>
    </>
  );
}
