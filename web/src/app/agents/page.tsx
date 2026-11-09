import Link from "next/link";
import { AgentActivity } from "@/components/AgentActivity";
import { AgentRunViewer } from "@/components/AgentRunViewer";
import { CollusionGraph, type Graph } from "@/components/CollusionGraph";
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
      <section className="section" aria-labelledby="why-graph">
        <div className="container-k grid gap-10 lg:grid-cols-[1fr_1.2fr] lg:items-center">
          <div className="space-y-4">
            <Eyebrow>Watchdog</Eyebrow>
            <h2 id="why-graph" className="section-title">Why a graph?</h2>
            <p className="text-lg leading-8">
              Matching rewards many different people backing a project, so one person with five accounts could get five votes. A single account looks normal. The pattern shows up only when you draw who gave to what: a tight group of new donors all backing the same few projects, and little else.
            </p>
            <p>
              The Watchdog flags such a cluster and freezes matching for those projects (never the donations). A person looks at the graph and decides. If they confirm it, the group counts as <strong>one person, one voice</strong> in matching. Nobody is refunded or banned by this step.
            </p>
          </div>
          <CollusionGraph graph={SAMPLE_RING} clusterIds={[21, 22, 23, 24]} title="Sample ring" />
        </div>
      </section>
    </>
  );
}

// A made-up example: four new donors (21–24) all back the same two projects; donors 7 and 9 give widely.
const SAMPLE_RING: Graph = {
  nodes: [
    ...[7, 9, 21, 22, 23, 24].map((id) => ({ id, type: "donor", label: `Donor ${id}` })),
    { id: 101, type: "project", label: "Sample library" },
    { id: 102, type: "project", label: "Sample water point" },
    { id: 103, type: "project", label: "Sample clinic" },
    { id: 104, type: "project", label: "Sample school meals" },
  ],
  edges: [
    ...[21, 22, 23, 24].flatMap((d) => [
      { source: d, target: 101, weight: 5 },
      { source: d, target: 102, weight: 5 },
    ]),
    { source: 7, target: 103, weight: 20 },
    { source: 7, target: 101, weight: 10 },
    { source: 9, target: 104, weight: 15 },
    { source: 9, target: 103, weight: 5 },
  ],
};
