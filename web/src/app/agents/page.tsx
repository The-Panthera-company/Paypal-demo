import Link from "next/link";
import { AgentActivity } from "@/components/AgentActivity";
import { AgentRunViewer } from "@/components/AgentRunViewer";
import { PageTitle } from "@/components/PageTitle";
import { Eyebrow } from "@/components/ui";
import { fetchAgentActivity, fetchAgentRun, fetchAgentRuns, type AgentActivity as Activity, type AgentRun } from "@/lib/agent-trace";

export const dynamic = "force-dynamic";

// Public Agent Trace: what the agent did, step by step, and what the rules allowed. Uses the
// public endpoints only (no donor names or ids).
export default async function AgentsPage({ searchParams }: { searchParams: Promise<{ run?: string }> }) {
  const { run: raw } = await searchParams;
  const runId = raw && /^\d+$/.test(raw) ? Number(raw) : undefined;
  const [run, runs, activity] = await Promise.all([
    (runId ? fetchAgentRun(runId) : fetchAgentRuns(1).then((r) => r[0])).catch(() => undefined) as Promise<AgentRun | undefined>,
    fetchAgentRuns(8).catch(() => [] as AgentRun[]),
    fetchAgentActivity(50).catch(() => [] as Activity[]),
  ]);

  return (
    <>
      <PageTitle title="Agent trace" crumb="Agents" />
      <section className="section bg-surface-alt">
        <div className="container-k space-y-10">
          <div className="max-w-3xl">
            <Eyebrow>Rules decide, agents explain</Eyebrow>
            <h2 className="section-title">What the agent did, and what the rules allowed.</h2>
            <p className="mt-3 text-lg leading-8">
              Every step a Giving Agent takes is recorded: the projects it read, how it scored them, what it asked to give, and what the rules engine allowed or blocked. Donor names and ids are never shown.
            </p>
          </div>

          <div className="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
            <section aria-labelledby="run-title" className="space-y-4">
              <h2 id="run-title" className="text-2xl">
                {runId ? `Run #${runId}` : "Latest run"}
              </h2>
              <AgentRunViewer runId={runId} initial={run ?? null} />
              {runs.length > 1 && (
                <nav aria-label="Recent runs" className="flex flex-wrap gap-2 text-sm">
                  <span className="self-center">Recent runs:</span>
                  {runs.map((r) => (
                    <Link
                      key={r.id}
                      href={`/agents?run=${r.id}`}
                      aria-current={run?.id === r.id ? "page" : undefined}
                      className={`min-h-9 px-3 leading-9 ${run?.id === r.id ? "bg-ink text-white" : "bg-white text-ink ring-1 ring-line hover:ring-primary"}`}
                    >
                      #{r.id}
                    </Link>
                  ))}
                </nav>
              )}
            </section>
            <section aria-labelledby="activity-title" className="space-y-4">
              <h2 id="activity-title" className="text-2xl">
                Recent activity <span className="ml-2 align-middle text-xs font-bold uppercase tracking-[2px] text-growth">● live</span>
              </h2>
              <AgentActivity initial={activity} />
            </section>
          </div>
        </div>
      </section>
    </>
  );
}
