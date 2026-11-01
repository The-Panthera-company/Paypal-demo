import { notFound } from "next/navigation";
import { CategoryBadge, ProgressBar, Stat, UrgencyBadge } from "@/components/ui";
import { formatMoney, getProject } from "@/lib/api";

// Milestones, story feed and documents come in issue #11; PayPal button in #14.
export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const p = await getProject(id);
  if (!p) notFound();
  const pct = (p.raised.amount / p.goal.amount) * 100;

  return (
    <article className="grid gap-8 lg:grid-cols-[1.6fr_1fr]">
      <div className="space-y-6">
        <div className="flex flex-wrap gap-2">
          <CategoryBadge id={p.categoryId} />
          <UrgencyBadge level={p.urgency} />
        </div>
        <div>
          <h1 className="text-3xl font-bold">{p.title}</h1>
          <p className="mt-1 text-sm text-muted">Facilitated by {p.facilitator} · {p.facets.region}</p>
        </div>
        <p className="max-w-[65ch] text-lg">{p.summary}</p>
        <section className="space-y-2">
          <h2 className="text-xl font-semibold">Impact updates</h2>
          <p className="text-sm text-muted">Receipts and photos appear here when each milestone is released.</p>
        </section>
      </div>

      <aside className="h-fit space-y-4 rounded-xl border border-line bg-surface p-5 lg:sticky lg:top-20">
        <div className="tabular text-3xl font-bold">{formatMoney(p.raised)}</div>
        <div className="text-sm text-muted">raised of {formatMoney(p.goal)} goal</div>
        <ProgressBar value={pct} label="Funding progress" />
        <div className="grid grid-cols-2 gap-3">
          <Stat value={String(p.backerCount)} label="backers" />
          <Stat value={`${Math.round(pct)}%`} label="funded" />
        </div>
        <button
          disabled
          className="min-h-12 w-full rounded-lg bg-primary px-5 font-medium text-white opacity-60"
          title="PayPal button arrives in issue #14"
        >
          Donate with PayPal
        </button>
        <p className="text-xs text-muted">Your name stays private unless you opt in to the leaderboard.</p>
      </aside>
    </article>
  );
}
