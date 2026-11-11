import { notFound } from "next/navigation";
import { PageTitle } from "@/components/PageTitle";
import { assignPhotos, CategoryArt, ProgressBar, StatBox } from "@/components/ui";
import Link from "next/link";
import { DonatePanel } from "@/components/DonatePanel";
import { MilestoneTimeline } from "@/components/MilestoneTimeline";
import { ProjectCard } from "@/components/ProjectCard";
import { Countdown } from "@/components/Countdown";
import { ProjectTabs } from "@/components/ProjectTabs";
import { TeamRoster } from "@/components/TeamRoster";
import { boughtTitle, fetchProjectProcurements, type Procurement } from "@/lib/procurement";
import { LineItems } from "@/components/PurchaseRequests";
import { daysLeft, formatDate, formatMoney, getImpactUpdates, getProject, getProjects, getRound, getSimilarProjects } from "@/lib/api";
import { getProjectTeam } from "@/lib/project-team";

// Krowd single-project layout, with the PayPal donate panel (#14).
export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const p = await getProject(id);
  if (!p) notFound();
  const pct = Math.round((p.raised.amount / p.goal.amount) * 100);
  const [updates, similar, round, procurements] = await Promise.all([getImpactUpdates(p.id), getSimilarProjects(p), getRound(), fetchProjectProcurements(p.id, { next: { revalidate: 60 } } as RequestInit).catch(() => [] as Procurement[])]);
  const bought = procurements.filter((x) => x.status === "paid");

  // Same photo as the project's card on Explore and Home (photos are assigned across the list)
  const photo = assignPhotos(await getProjects().catch(() => []))[p.id];
  const team = getProjectTeam(p);
  const milestones = [...(p.milestones ?? [])].sort((a, b) => a.seq - b.seq);
  const fundsTotal = milestones.reduce((t, m) => t + m.amount.amount, 0) || p.goal.amount;
  const released = milestones.filter((m) => m.status === "released");
  const nextMilestone = milestones.find((m) => m.status !== "released");
  const nextReport = nextMilestone?.dueDate ?? null;
  const statusText = { open: "Not started", evidence_submitted: "Evidence being checked", held: "Held for an admin", released: "Released" } as const;
  const cause = p.facets.cause.charAt(0).toUpperCase() + p.facets.cause.slice(1);

  const story = (
    <div className="space-y-12">
      <section>
        <h2 className="mb-4 text-3xl">Background</h2>
        <p className="text-lg leading-9">{p.summary || `${cause} for ${p.facets.group.toLowerCase()} in ${p.facets.region}.`}</p>
        <dl className="mt-6 grid gap-4 sm:grid-cols-3">
          {[
            ["Cause", cause],
            ["Who it helps", p.facets.group],
            ["Where", p.facets.region],
          ].map(([k, v]) => (
            <div key={k} className="border-l-4 border-cobalt-green bg-surface-alt p-4">
              <dt className="text-xs font-bold uppercase tracking-[2px]">{k}</dt>
              <dd className="mt-1 font-medium capitalize text-ink">{v}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section>
        <h2 className="mb-4 text-3xl">What they&apos;re doing</h2>
        {milestones.length === 0 ? (
          <p className="text-lg leading-9">The project hasn&apos;t published its steps yet.</p>
        ) : (
          <ol className="space-y-3">
            {milestones.map((m) => (
              <li key={m.id} className="flex items-start gap-4 bg-white p-4">
                <span className="tabular grid size-10 shrink-0 place-items-center bg-primary font-display text-xl text-white">{m.seq}</span>
                <div className="flex-1">
                  <p className="font-medium text-ink">{m.title}</p>
                  <p className="text-sm">
                    {statusText[m.status]}
                    {m.dueDate && <> · due {formatDate(m.dueDate)}</>}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-3xl">How the money is used</h2>
        <p className="mb-5">Money is released step by step, only after receipts and photos for each step pass the checks.</p>
        {milestones.length > 0 && (
          <>
            <div className="flex h-4 overflow-hidden bg-line" aria-hidden>
              {milestones.map((m, i) => (
                <span key={m.id} className={["bg-primary", "bg-growth", "bg-cobalt-green", "bg-cat-education"][i % 4]} style={{ width: `${(m.amount.amount / fundsTotal) * 100}%` }} />
              ))}
            </div>
            <table className="mt-4 w-full text-left">
              <caption className="sr-only">Budget by step</caption>
              <thead>
                <tr className="border-b border-line text-sm">
                  <th className="py-2 font-medium">Step</th>
                  <th className="py-2 text-right font-medium">Amount</th>
                  <th className="py-2 text-right font-medium">Share</th>
                </tr>
              </thead>
              <tbody>
                {milestones.map((m, i) => (
                  <tr key={m.id} className="border-b border-line">
                    <td className="py-3 text-ink">
                      <span className={`mr-2 inline-block size-3 ${["bg-primary", "bg-growth", "bg-cobalt-green", "bg-cat-education"][i % 4]}`} aria-hidden />
                      {m.title}
                    </td>
                    <td className="tabular py-3 text-right text-ink">{formatMoney(m.amount)}</td>
                    <td className="tabular py-3 text-right">{Math.round((m.amount.amount / fundsTotal) * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        <p className="mt-4 text-sm">This round&apos;s matching is added to the next step that hasn&apos;t been paid yet.</p>
      </section>
    </div>
  );

  const timeline = [
    p.verifiedAt && { date: p.verifiedAt, title: "Project verified", body: "An admin checked the organisation and its plan.", done: true },
    ...released.map((m) => ({ date: m.dueDate, title: `${m.title}: released`, body: `${formatMoney(m.amount)} paid after its evidence was checked.`, done: true })),
    nextMilestone && {
      date: nextMilestone.dueDate,
      title: `Now: ${nextMilestone.title}`,
      body: statusText[nextMilestone.status] + (nextMilestone.status === "evidence_submitted" ? ": the receipts and photos are with the checkers." : "."),
      done: false,
      now: true,
    },
  ].filter(Boolean) as { date: string | null; title: string; body: string; done: boolean; now?: boolean }[];

  const updatesPanel = (
    <div className="space-y-10">
      <div className="flex flex-wrap items-center gap-4 border-l-4 border-accent bg-ink p-5 text-white">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2" aria-hidden>
          <path d="M8 3v3M16 3v3M4 8h16M5 5h14v15H5z" />
        </svg>
        <p className="flex-1">
          <span className="block text-xs font-bold uppercase tracking-[2px] text-cobalt-green">Next progress report</span>
          {nextReport ? (
            <>
              Expected by <strong className="text-accent">{formatDate(nextReport)}</strong>, with receipts and photos for &ldquo;{nextMilestone?.title}&rdquo;.
            </>
          ) : released.length && released.length === milestones.length ? (
            "Every step is complete. The final report is below."
          ) : (
            "The project will set a date for its next report."
          )}
        </p>
      </div>

      <section>
        <h2 className="mb-6 text-3xl">Status so far</h2>
        <ol className="space-y-6 border-l-2 border-line pl-6">
          {timeline.map((t, i) => (
            <li key={i} className="relative">
              <span className={`absolute -left-[33px] top-1 size-4 ${t.now ? "animate-pulse bg-accent ring-4 ring-accent/30" : t.done ? "bg-growth" : "bg-line"}`} aria-hidden />
              {t.date && <p className="text-sm">{formatDate(t.date)}</p>}
              <h3 className="text-xl">{t.title}</h3>
              <p>{t.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h2 className="mb-6 text-3xl">Updates with evidence</h2>
        {bought.length > 0 && (
          <ol className="mb-6 space-y-4" aria-label="Purchases paid through PayPal">
            {bought.map((b) => (
              <li key={b.id} className="border-l-4 border-growth bg-white p-5">
                <p className="text-sm">
                  {formatDate(b.updated_at)} · Bought by the platform · paid to the supplier through PayPal
                </p>
                <h3 className="text-xl">
                  {boughtTitle(b)} — PayPal {b.paypal_batch_id ? <>batch <code className="text-base text-primary">{b.paypal_batch_id}</code></> : "payout"}
                </h3>
                <p>
                  {b.supplier_name ?? "Supplier"} · <strong className="tabular text-ink">{formatMoney({ amount: b.amount_cents ?? 0, currency: b.currency })}</strong>
                </p>
                {b.line_items.length > 0 && (
                  <details className="mt-2 text-sm">
                    <summary className="cursor-pointer text-primary">Line items</summary>
                    <LineItems p={b} />
                  </details>
                )}
                {b.receipt_url && (
                  <a href={b.receipt_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-sm font-bold text-primary underline-offset-4 hover:underline">
                    PayPal receipt ↗
                  </a>
                )}
              </li>
            ))}
          </ol>
        )}
        {updates.length === 0 && bought.length === 0 ? (
          <p className="border border-dashed border-line p-6">No milestone released yet. Updates with receipts and photos appear here.</p>
        ) : updates.length === 0 ? null : (
          <ol className="space-y-6">
            {updates.map((u) => (
              <li key={u.id} className="bg-white p-5">
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
      </section>

      <MilestoneTimeline milestones={milestones} />
    </div>
  );

  return (
    <>
      <PageTitle title="Project details" crumb={p.title} main={false} />
      <section className="bg-surface-alt pb-20 pt-12 lg:pb-28 lg:pt-[100px]">
        <div className="container-k grid gap-10 lg:grid-cols-2">
          <div className="aspect-[4/3]">
            <CategoryArt id={p.categoryId} seed={p.id} photo={photo} label={`Photo for ${p.title}`} />
          </div>
          <div>
            <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-ink">
              <span className="tag">{p.categoryId}</span>
              <span className="flex items-center gap-1.5">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M12 21s7-6.5 7-12a7 7 0 00-14 0c0 5.5 7 12 7 12zM12 6a3 3 0 100 6 3 3 0 000-6z" />
                </svg>
                {p.facets.region}
              </span>
              {p.verifiedAt && (
                <span className="flex items-center gap-1.5">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                    <path d="M8 3v3M16 3v3M4 8h16M5 5h14v15H5z" />
                  </svg>
                  Verified {formatDate(p.verifiedAt)}
                </span>
              )}
            </div>
            <h1 className="mb-3 text-4xl">{p.title}</h1>
            <Link href={`/projects/${p.id}/evidence`} className="mb-3 inline-block text-sm font-bold text-primary underline-offset-4 hover:underline">
              Owner tools →
            </Link>
            <p className="mb-6 text-lg leading-8">{p.summary}</p>
            <div className="mb-6 grid grid-cols-3 gap-3 sm:gap-[30px]">
              <StatBox value={formatMoney(p.raised)} label="Raised" />
              <StatBox value={String(p.backerCount)} label="Backers" />
              <StatBox value={String(daysLeft(p))} label="Days left" />
            </div>
            <div className="mb-2 flex justify-between text-sm font-medium text-ink">
              <span>
                Raised of <span className="text-brand">{formatMoney(p.goal)}</span>
              </span>
              <span className="tabular">{pct}%</span>
            </div>
            <ProgressBar value={pct} label="Funding progress" />

            {/* This project's matching round */}
            <div className="mt-8 flex flex-wrap items-end justify-between gap-4 bg-ink p-5 text-white">
              <div>
                <p className="text-xs font-bold uppercase tracking-[2px] text-cobalt-green">{round.name}</p>
                <p className="mt-1">
                  {p.matchingFrozen ? (
                    "Matching is paused while this project is reviewed."
                  ) : p.projectedMatch ? (
                    <>
                      Projected matching for this project: <strong className="tabular text-accent">{formatMoney(p.projectedMatch)}</strong>
                    </>
                  ) : (
                    "Gifts made before the round closes count for matching."
                  )}
                </p>
              </div>
              <Countdown endsAt={round.endsAt} small onDark label="Round closes in" />
            </div>

            <div className="mt-8 flex flex-wrap gap-4">
              <a href="#donate-box" className="btn">
                Back this project
              </a>
              <a href="#about" className="btn btn-2">
                Read the story first
              </a>
            </div>
          </div>
        </div>
      </section>

      <section id="about" className="pb-16 lg:pb-[120px]">
        <div className="container-k -mt-8 grid gap-10 lg:grid-cols-[1fr_380px]">
          <ProjectTabs
            tabs={[
              { id: "story", label: "Story", content: story },
              { id: "updates", label: "Updates", badge: String(updates.length + released.length || ""), content: updatesPanel },
              { id: "team", label: "Team", badge: String(team.members.length), content: <TeamRoster members={team.members} sample={team.sample} /> },
            ].map((t) => ({ ...t, badge: t.badge || undefined }))}
          />
          <aside id="donate-box" className="scroll-mt-32 lg:pt-[64px]">
            <div className="space-y-4 lg:sticky lg:top-32">
              <h2 className="text-2xl">Back this project</h2>
              <DonatePanel projectId={p.id} projectTitle={p.title} />
              <p className="text-sm">Your name stays private unless you opt in to the leaderboard.</p>
              <p className="text-sm">
                Something wrong with this project?{" "}
                <Link href={`/report?project=${p.id}`} className="font-medium text-brand underline">
                  Report it
                </Link>{" "}
                and an admin will review it.
              </p>
            </div>
          </aside>
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
        <a href="#donate-box" className="btn !min-h-12 !px-6">
          Back this
        </a>
      </div>
    </>
  );
}
