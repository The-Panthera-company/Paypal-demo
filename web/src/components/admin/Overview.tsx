import { plainReport } from "@/components/AgentReport";
import Link from "next/link";
import type { GlobePin } from "@/components/GlobeBackdrop";
import { GlobeBackdrop } from "@/components/GlobeBackdrop";
import { RollingNumber } from "@/components/RollingNumber";
import type { AdminData, Dashboard } from "@/lib/admin";
import { formatMoney } from "@/lib/api";
import type { Category, Leaderboard, Project } from "@/lib/types";

const CAT: Record<string, string> = { health: "bg-cat-health", education: "bg-cat-education", environment: "bg-cat-environment", water: "bg-cat-water" };

// Admin overview: the usual crowdfunding back-office layout (key numbers, what needs a person,
// money in/out, funding by category, recent activity) plus this platform's own parts: the
// project map, Watchdog cases, held tranches and the reconciliation checks.
export function Overview({ data, dash, projects, lb, categories, globe }: { data: AdminData; dash: Dashboard; projects: Project[]; lb: Leaderboard; categories: Category[]; globe: GlobePin[] }) {
  const cur = projects[0]?.goal.currency ?? "USD";
  const m = (a: number) => formatMoney({ amount: a, currency: cur });
  const raised = projects.reduce((s, p) => s + p.raised.amount, 0);
  const backers = projects.reduce((s, p) => s + p.backerCount, 0);
  const projected = lb.rows.reduce((s, r) => s + r.match.amount, 0);
  const t = dash.totals;
  const errors = dash.issues.filter((i) => i.severity === "error");
  const warnings = dash.issues.filter((i) => i.severity === "warning");
  const openCases = data.cases.filter((c) => c.status === "open");

  const kpis: [string, string, string?][] = [
    [m(raised), "raised by the crowd"],
    [String(backers), "backers"],
    [m(lb.pool.amount), "matching pool", `${m(projected)} projected`],
    [m(t?.released ?? 0), "released to projects"],
    [m(t?.paidOut ?? 0), "paid out by PayPal", t && t.releasedNotPaid > 0 ? `${m(t.releasedNotPaid)} waiting` : undefined],
  ];

  const todo = [
    { n: openCases.length, label: "Watchdog cases open", body: "Matching is frozen until you clear or confirm.", href: "/admin?tab=cases", tone: "bg-cat-health" },
    { n: data.queue.length, label: "projects to verify", body: "Not listed until a person checks them.", href: "/admin?tab=verify", tone: "bg-primary" },
    { n: data.milestones.length, label: "tranches held", body: "Evidence failed a check or the amount needs approval.", href: "/admin?tab=milestones", tone: "bg-cat-education" },
    { n: errors.length, label: "reconciliation errors", body: errors[0]?.detail ?? "Money in and out add up.", href: "#reconciliation", tone: errors.length ? "bg-cat-health" : "bg-growth" },
  ];

  const byCat = categories.map((c) => ({ c, raised: projects.filter((p) => p.categoryId === c.id).reduce((s, p) => s + p.raised.amount, 0), n: projects.filter((p) => p.categoryId === c.id).length }));
  const maxCat = Math.max(1, ...byCat.map((x) => x.raised));
  const flow = t ? [
    ["Received via PayPal", t.received, "bg-primary"],
    ["Released to projects", t.released, "bg-growth"],
    ["Paid out", t.paidOut, "bg-cobalt-green"],
    ["Agent budgets unspent", t.agentUnspent, "bg-accent"],
  ] as const : [];
  const maxFlow = Math.max(1, ...flow.map((f) => f[1]));

  return (
    <div className="space-y-6">
      {/* Key numbers */}
      <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-3 xl:grid-cols-5">
        {kpis.map(([v, l, sub]) => (
          <div key={l} className="bg-white p-5">
            <div className="font-display text-2xl text-ink lg:text-3xl">
              <RollingNumber value={v} />
            </div>
            <div className="text-sm">{l}</div>
            {sub && <div className="mt-1 text-xs text-primary">{sub}</div>}
          </div>
        ))}
      </div>

      {/* Needs a person */}
      <section aria-labelledby="todo" className="space-y-3">
        <h2 id="todo" className="text-2xl">Needs your attention</h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {todo.map((x) => (
            <Link key={x.label} href={x.href} className="group flex gap-4 bg-white p-5 ring-1 ring-line transition-shadow hover:shadow-[0_15px_35px_rgba(11,46,51,0.1)]">
              <span className={`tabular grid size-12 shrink-0 place-items-center font-display text-2xl text-white ${x.n ? x.tone : "bg-line text-ink"}`}>{x.n}</span>
              <span>
                <span className="block font-medium text-ink group-hover:text-primary">{x.label}</span>
                <span className="block text-sm">{x.body}</span>
              </span>
            </Link>
          ))}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
        {/* Money in and out */}
        <section id="reconciliation" aria-labelledby="money" className="scroll-mt-32 space-y-4 bg-white p-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="money" className="text-2xl">Money in and out</h2>
            <span className={`px-2 text-xs font-bold uppercase leading-6 tracking-wider ${errors.length ? "bg-cat-health text-white" : "bg-cobalt-green text-ink"}`}>
              {errors.length ? `${errors.length} error${errors.length > 1 ? "s" : ""}` : "Reconciled"}
            </span>
          </div>
          {flow.length === 0 ? (
            <p className="text-sm">Reconciliation isn&apos;t available (admin token not set, or the API can&apos;t be reached).</p>
          ) : (
            <ul className="space-y-3">
              {flow.map(([l, v, c]) => (
                <li key={l} className="grid grid-cols-[170px_1fr_auto] items-center gap-3 text-sm">
                  <span className="text-ink">{l}</span>
                  <span className="h-3 bg-surface-alt" aria-hidden>
                    <span className={`block h-full ${c}`} style={{ width: `${(v / maxFlow) * 100}%`, minWidth: v ? 4 : 0 }} />
                  </span>
                  <span className="tabular font-medium text-ink">{m(v)}</span>
                </li>
              ))}
            </ul>
          )}
          {[...errors, ...warnings].length > 0 && (
            <ul className="space-y-2 border-t border-line pt-4">
              {[...errors, ...warnings].map((i) => (
                <li key={i.check} className={`border-l-4 bg-surface-alt p-3 text-sm text-ink ${i.severity === "error" ? "border-cat-health" : "border-cat-education"}`}>
                  <strong>{i.detail}</strong> ({i.count}) <span className="text-text">· {i.check.replaceAll("_", " ")}</span>
                </li>
              ))}
            </ul>
          )}
          {dash.payouts.length > 0 && (
            <div className="border-t border-line pt-4">
              <h3 className="mb-2 text-lg">Payout batches</h3>
              <ul className="divide-y divide-line text-sm">
                {dash.payouts.slice(0, 5).map((b) => (
                  <li key={b.batch} className="flex items-center justify-between gap-3 py-2">
                    <span className="truncate text-ink">{b.batch}</span>
                    <span className="tabular">{m(b.amount)}</span>
                    <span className={`px-2 text-[11px] font-bold uppercase leading-5 tracking-wider ${b.pending ? "bg-accent text-ink" : "bg-cobalt-green text-ink"}`}>{b.pending ? `${b.pending} pending` : b.status}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {/* Project map */}
        <section aria-labelledby="map" className="relative overflow-hidden bg-ink p-6 text-white">
          <h2 id="map" className="text-2xl text-white">Projects on the map</h2>
          <p className="text-sm text-cobalt-green">
            {globe.length} projects in {new Set(globe.map((g) => g.place)).size} places. Point at a pin for details.
          </p>
          <div className="mx-auto mt-2 max-w-[420px]">
            <GlobeBackdrop pins={globe} />
          </div>
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        {/* Funding by category */}
        <section aria-labelledby="cats" className="space-y-4 bg-white p-6">
          <h2 id="cats" className="text-2xl">Funding by category</h2>
          <ul className="space-y-3">
            {byCat.map(({ c, raised: r, n }) => (
              <li key={c.id} className="grid grid-cols-[120px_1fr_auto] items-center gap-3 text-sm">
                <span className="text-ink">
                  {c.name} <span className="text-text">({n})</span>
                </span>
                <span className="h-3 bg-surface-alt" aria-hidden>
                  <span className={`block h-full ${CAT[c.id] ?? "bg-primary"}`} style={{ width: `${(r / maxCat) * 100}%`, minWidth: r ? 4 : 0 }} />
                </span>
                <span className="tabular font-medium text-ink">{m(r)}</span>
              </li>
            ))}
          </ul>
          <p className="text-sm">
            Top of the matching round: <strong className="text-ink">{[...lb.rows].sort((a, b) => a.rank - b.rank)[0]?.title ?? "none yet"}</strong>.{" "}
            <Link href="/leaderboard?tab=projects" className="font-medium text-primary underline">
              Leaderboard
            </Link>
          </p>
        </section>

        {/* Recent activity */}
        <section aria-labelledby="activity" className="space-y-3 bg-white p-6">
          <div className="flex items-baseline justify-between">
            <h2 id="activity" className="text-2xl">Recent activity</h2>
            <Link href="/admin?tab=log" className="text-sm font-medium text-primary underline">
              Full agent log
            </Link>
          </div>
          {data.audit.length === 0 ? (
            <p className="text-sm">Nothing logged yet.</p>
          ) : (
            <ol className="space-y-3">
              {data.audit.slice(0, 7).map((a) => (
                <li key={a.id} className="flex gap-3 text-sm">
                  <span className="mt-1.5 size-2 shrink-0 bg-growth" aria-hidden />
                  <span>
                    <span className="font-medium text-ink">{a.actor}</span> · {a.action.replaceAll("_", " ")}
                    {a.reason && <span className="block whitespace-pre-line text-text">{a.reason.length > 220 ? `${plainReport(a.reason).slice(0, 220).trimEnd()}…` : plainReport(a.reason)}</span>}
                    <span className="block text-xs text-text">{new Date(a.createdAt).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                  </span>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}
