import Link from "next/link";
import { notFound } from "next/navigation";
import { PageTitle } from "@/components/PageTitle";
import { RollingNumber } from "@/components/RollingNumber";
import { getRoundResults } from "@/lib/api";

export const revalidate = 60;

// Round results: totals, then projected vs final match per project. Final fills in at close.
export default async function RoundResultsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const r = await getRoundResults(id);
  if (!r) notFound();
  const m = (c: number) => new Intl.NumberFormat(undefined, { style: "currency", currency: r.currency, maximumFractionDigits: 0 }).format(c / 100);
  const rows = [...r.rows].sort((a, b) => (b.final ?? b.projected) - (a.final ?? a.projected));

  return (
    <>
      <PageTitle title={`${r.name} results`} crumb="Round results" />
      <section className="section">
        <div className="container-k space-y-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className={`px-3 text-xs font-bold uppercase leading-7 tracking-[2px] ${r.isFinal ? "bg-ink text-white" : "bg-cobalt-green text-ink"}`}>{r.isFinal ? "Final results" : `Projected · round ${r.status}`}</span>
            <p className="text-sm">{r.isFinal ? "The round has closed; these numbers are final." : "The final column fills in when the round closes."}</p>
          </div>

          <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-3 lg:grid-cols-6">
            {(
              [
                [m(r.pool), "matching pool"],
                [m(r.sponsored), "of which sponsors"],
                [m(r.matched), r.isFinal ? "matched" : "projected match"],
                [m(r.unspent), "left unspent (caps)"],
                [m(r.raised), "raised by the crowd"],
                [String(r.backers), "backers"],
              ] as const
            ).map(([v, l]) => (
              <div key={l} className="bg-white p-5 text-center">
                <div className="font-display text-2xl text-ink">
                  <RollingNumber value={v} />
                </div>
                <div className="text-sm">{l}</div>
              </div>
            ))}
          </div>

          <div className="overflow-x-auto bg-white ring-1 ring-line">
            <table className="w-full min-w-[640px] text-left text-sm">
              <caption className="sr-only">Projected and final match per project</caption>
              <thead className="bg-surface-alt text-ink">
                <tr>
                  <th className="p-3 font-medium">Project</th>
                  <th className="p-3 text-right font-medium">Backers</th>
                  <th className="p-3 text-right font-medium">Raised</th>
                  <th className="p-3 text-right font-medium">Projected match</th>
                  <th className="p-3 text-right font-medium">Final match</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((x) => (
                  <tr key={x.projectId} className="border-t border-line">
                    <td className="p-3">
                      <Link href={`/projects/${x.projectId}`} className="font-medium text-ink hover:text-primary hover:underline">
                        {x.title}
                      </Link>
                      <span className="block text-xs">{x.category}</span>
                    </td>
                    <td className="tabular p-3 text-right">{x.backers}</td>
                    <td className="tabular p-3 text-right">{m(x.raised)}</td>
                    <td className="tabular p-3 text-right">{m(x.projected)}</td>
                    <td className="tabular p-3 text-right font-bold text-ink">
                      {x.final === null ? <span className="font-normal text-text">at close</span> : m(x.final)}
                      {x.capped && <span className="ml-2 bg-cobalt-green px-1.5 text-[10px] font-bold uppercase tracking-wider text-ink">Capped</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Link href="/leaderboard?tab=projects" className="btn btn-2">
            Back to the leaderboard
          </Link>
        </div>
      </section>
    </>
  );
}
