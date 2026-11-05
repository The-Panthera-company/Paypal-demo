import Link from "next/link";
import { Avatar } from "@/components/Avatar";
import { LeaderboardOptIn } from "@/components/LeaderboardOptIn";
import { PageTitle } from "@/components/PageTitle";
import { EmptyState, StatBox } from "@/components/ui";
import { formatDate, formatMoney, getDonorReport, getProjects } from "@/lib/api";

export const dynamic = "force-dynamic";

const DONOR_ID = process.env.NEXT_PUBLIC_DEMO_DONOR_ID ?? "1";
const via = { PROJECT: "Direct gift", CATEGORY: "Category gift", AGENT: "Giving Agent" } as const;

// My Impact (#35): "where your money went". GET /donors/{id}/report, never cached.
export default async function ReportPage() {
  const [report, projects] = await Promise.all([getDonorReport(DONOR_ID), getProjects()]);

  if (!report) {
    return (
      <>
        <PageTitle title="My impact" crumb="My impact" />
        <section className="section">
          <div className="container-k">
            <EmptyState
              title="We couldn't find your donor account"
              body={`The demo donor (id ${DONOR_ID}) doesn't exist in the API yet.`}
              action={{ href: "/projects", label: "Explore projects" }}
            />
          </div>
        </section>
      </>
    );
  }

  const cur = report.totalGiven.currency;
  const m = (a: number) => formatMoney({ amount: a, currency: cur });
  const multiplier = report.totalGiven.amount > 0 ? report.matchUnlocked.amount / report.totalGiven.amount : 0;
  const backed = new Set(report.gifts.map((g) => g.projectId).filter(Boolean)).size;

  // Chart: given vs matching unlocked, per project
  const byProject = new Map<string, { title: string; given: number; match: number }>();
  for (const g of report.gifts) {
    const key = g.projectId ?? `via-${g.via}`;
    const row = byProject.get(key) ?? { title: g.projectTitle ?? via[g.via], given: 0, match: 0 };
    row.given += g.amount.amount;
    row.match += g.matchUnlocked.amount;
    byProject.set(key, row);
  }
  const rows = [...byProject.values()].sort((a, b) => b.given + b.match - (a.given + a.match));
  const max = Math.max(1, ...rows.map((r) => Math.max(r.given, r.match)));
  const title = (id: string) => projects.find((p) => p.id === id)?.title ?? "A project you backed";

  return (
    <>
      <PageTitle title="My impact" crumb="My impact" />
      <section className="section bg-surface-alt">
        <div className="container-k space-y-12">
          {report.sample && (
            <p className="border-l-4 border-growth bg-white p-3 text-sm text-ink">Sample report. Connect the core API to see your own gifts.</p>
          )}

          {report.gifts.length === 0 ? (
            <EmptyState
              title="No gifts yet"
              body="When you back a project, you'll see here where your money went, the matching it unlocked, and receipts as milestones are released."
              action={{ href: "/projects", label: "Back a project" }}
            />
          ) : (
            <>
              <div className="flex items-center gap-4">
                <Avatar seed={`donor-${report.donorId}`} anonymous={!report.showOnLeaderboard} name={`Donor ${report.donorId}`} size={64} label="Your avatar" />
                <div>
                  <p className="font-display text-2xl text-ink">Your giving so far</p>
                  <p className="text-sm">
                    {report.showOnLeaderboard ? "Shown on public pages with your avatar." : "Anonymous on public pages. Your avatar stays a pattern."}
                  </p>
                </div>
              </div>
              {/* Headline numbers */}
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <StatBox value={formatMoney(report.totalGiven)} label="You gave" />
                <StatBox value={formatMoney(report.matchUnlocked)} label="Matching you unlocked" />
                <StatBox value={String(backed)} label={backed === 1 ? "Project backed" : "Projects backed"} />
                <StatBox value={multiplier > 0 ? `×${(1 + multiplier).toFixed(1)}` : "–"} label="Total impact of each $1" />
              </div>
              {multiplier > 0 && (
                <p className="max-w-[70ch] text-lg leading-8 text-ink">
                  Because many people backed the same projects, every dollar you gave brought in about{" "}
                  <strong>{formatMoney({ amount: Math.round(multiplier * 100), currency: cur })}</strong> more from the matching pool.
                </p>
              )}

              {/* Chart */}
              <section className="space-y-4 bg-white p-6">
                <h2 className="text-2xl">Where your money went</h2>
                <div className="flex flex-wrap gap-5 text-sm" aria-hidden>
                  <span className="flex items-center gap-2"><span className="h-3 w-6 bg-primary" /> You gave</span>
                  <span className="flex items-center gap-2"><span className="h-3 w-6 bg-cobalt-green" /> Matching unlocked</span>
                </div>
                <table className="w-full">
                  <caption className="sr-only">Amount you gave and matching unlocked, per project</caption>
                  <thead className="sr-only">
                    <tr>
                      <th scope="col">Project</th>
                      <th scope="col">You gave</th>
                      <th scope="col">Matching unlocked</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.title} className="border-b border-line last:border-0">
                        <th scope="row" className="w-1/3 py-3 pr-4 text-left font-medium text-ink">
                          {r.title}
                        </th>
                        <td className="w-1/3 py-3 pr-2" colSpan={1}>
                          <div className="flex items-center gap-2">
                            <span className="h-4 bg-primary" style={{ width: `${(r.given / max) * 100}%`, minWidth: 4 }} aria-hidden />
                            <span className="tabular text-sm text-ink">{m(r.given)}</span>
                          </div>
                        </td>
                        <td className="w-1/3 py-3">
                          <div className="flex items-center gap-2">
                            <span className="h-4 bg-cobalt-green" style={{ width: `${(r.match / max) * 100}%`, minWidth: 4 }} aria-hidden />
                            <span className="tabular text-sm text-ink">{m(r.match)}</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-sm">Matching is projected until the round closes, then final. It is paid out with the project&apos;s next milestone.</p>
              </section>

              <div className="grid gap-8 lg:grid-cols-[1.3fr_1fr]">
                {/* Receipts */}
                <section className="space-y-4">
                  <h2 className="text-2xl">Your receipts</h2>
                  <ul className="space-y-3">
                    {report.gifts.map((g) => (
                      <li key={g.donationId} className="corner border border-line bg-white p-5" style={{ ["--corner-size" as string]: "12px" }}>
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-xs uppercase tracking-[2px]">Receipt #{g.donationId} · {via[g.via]}</p>
                            {g.projectId ? (
                              <Link href={`/projects/${g.projectId}`} className="font-display text-xl text-ink hover:text-primary hover:underline">
                                {g.projectTitle ?? title(g.projectId)}
                              </Link>
                            ) : (
                              <p className="font-display text-xl text-ink">{g.projectTitle ?? via[g.via]}</p>
                            )}
                          </div>
                          <span className={`px-2 text-xs font-bold uppercase leading-6 tracking-wider ${g.status === "captured" ? "bg-cobalt-green text-ink" : "bg-line text-ink"}`}>
                            {g.status === "captured" ? "Paid" : g.status}
                          </span>
                        </div>
                        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                          <div>
                            <dt>You gave</dt>
                            <dd className="tabular font-bold text-ink">{formatMoney(g.amount)}</dd>
                          </div>
                          <div>
                            <dt>Matching unlocked</dt>
                            <dd className="tabular font-bold text-ink">{formatMoney(g.matchUnlocked)}</dd>
                          </div>
                        </dl>
                        <p className="mt-2 text-xs">Paid through PayPal (sandbox). PayPal also emails you its own receipt.</p>
                      </li>
                    ))}
                  </ul>
                </section>

                <div className="space-y-8">
                  {/* Giving Agent */}
                  <section className="space-y-3 bg-ink p-6 text-white">
                    <h2 className="flex items-center gap-3 text-2xl text-white">
                      <Avatar name="Giving Agent" seed="giving-agent" size={36} label="Giving Agent" />
                      Your Giving Agent
                    </h2>
                    {report.agentReport ? (
                      <p className="leading-7 text-cobalt-green">{report.agentReport}</p>
                    ) : (
                      <p className="text-footer-text">No agent runs yet. Set your rules and it will explain every choice here.</p>
                    )}
                    <Link href="/mandate" className="btn mt-2">
                      Giving Agent settings
                    </Link>
                  </section>

                  {/* Privacy */}
                  <section className="space-y-3 bg-white p-6">
                    <h2 className="text-xl">Privacy</h2>
                    <LeaderboardOptIn donorId={report.donorId} initial={report.showOnLeaderboard} sample={report.sample} />
                  </section>
                </div>
              </div>

              {/* Impact feed */}
              <section className="space-y-4">
                <h2 className="text-2xl">Proof from the projects you backed</h2>
                {report.updates.length === 0 ? (
                  <p className="border border-dashed border-line bg-white p-6">
                    No milestone released yet. When a project you backed uploads receipts and photos that pass the checks, they appear here.
                  </p>
                ) : (
                  <ol className="space-y-6 border-l-2 border-line pl-6">
                    {report.updates.map((u) => (
                      <li key={u.id} className="relative">
                        <span className="absolute -left-[31px] top-1.5 size-3 bg-growth" aria-hidden />
                        <p className="text-sm">
                          {formatDate(u.date)} · {title(u.projectId)}
                        </p>
                        <h3 className="text-xl">{u.title}</h3>
                        <p>{u.caption}</p>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </>
          )}
        </div>
      </section>
    </>
  );
}
