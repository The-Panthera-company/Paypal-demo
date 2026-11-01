import Link from "next/link";
import { ProjectCard } from "@/components/ProjectCard";
import { Stat } from "@/components/ui";
import { formatMoney, getCategories, getProjects } from "@/lib/api";

export default async function Home() {
  const [categories, projects] = await Promise.all([getCategories(), getProjects()]);
  const raised = projects.reduce((s, p) => s + p.raised.amount, 0);
  const backers = projects.reduce((s, p) => s + p.backerCount, 0);
  const urgent = projects.filter((p) => p.urgency >= 4).slice(0, 3);

  return (
    <div className="space-y-12">
      <section className="space-y-5">
        <h1 className="max-w-2xl text-4xl font-bold leading-tight">Small gifts, decided together.</h1>
        <p className="max-w-[60ch] text-lg text-muted">
          Back verified community projects through PayPal. Projects with many backers earn the biggest share of the
          matching pool, and every payout is released only with receipts.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link href="/projects" className="inline-flex min-h-12 items-center rounded-lg bg-primary px-5 font-medium text-white hover:bg-primary-hover">
            Find a project
          </Link>
          <Link href="/mandate" className="inline-flex min-h-12 items-center rounded-lg border border-line bg-surface px-5 font-medium hover:border-primary">
            Set up a Giving Agent
          </Link>
        </div>
      </section>

      <section aria-label="Platform totals" className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Stat value={formatMoney({ amount: raised, currency: "USD" })} label="raised this round" />
        <Stat value={String(backers)} label="backers" />
        <Stat value={String(projects.length)} label="verified projects" />
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Categories</h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {categories.map((c) => (
            <Link
              key={c.id}
              href={`/projects?category=${c.id}`}
              className="rounded-xl border border-line bg-surface p-5 hover:border-primary"
              style={{ borderTop: `4px solid var(--color-cat-${c.id})` }}
            >
              <div className="text-lg font-semibold">{c.name}</div>
              <div className="text-sm text-muted">{c.projectCount} projects</div>
              <div className="tabular mt-3 text-sm font-medium">{formatMoney(c.raised)} raised</div>
            </Link>
          ))}
        </div>
      </section>

      {urgent.length > 0 && (
        <section className="space-y-4">
          <h2 className="text-2xl font-semibold">Urgent and overlooked</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {urgent.map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
