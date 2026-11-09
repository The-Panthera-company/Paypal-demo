import Link from "next/link";
import { getGlobePins } from "@/lib/globe";

import { AuditGrid, CasesGrid, MilestonesGrid, VerificationGrid } from "@/components/admin/AdminGrids";
import { PageTitle } from "@/components/PageTitle";
import { listProcurement, getAgentStatus, getAuditChain, verifyAuditChain, getAdminData, getDashboard, getProjectDocuments, listRounds } from "@/lib/admin";
import { OwnerTokenButton } from "@/components/admin/OwnerTokenButton";
import { RoundsPanel } from "@/components/admin/RoundsPanel";
import { RefundPanel } from "@/components/admin/RefundPanel";
import { getCategories, getLeaderboard, getProjects } from "@/lib/api";
import { Overview } from "@/components/admin/Overview";
import { AgentSwitch } from "@/components/admin/AgentSwitch";
import { ProcurementPanel } from "@/components/admin/ProcurementPanel";
import { TrustPanel } from "@/components/admin/TrustPanel";
import { CollusionCases } from "@/components/admin/CollusionCases";
import { hasRingGraph } from "@/components/CollusionGraph";

export const dynamic = "force-dynamic";

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "cases", label: "Watchdog cases" },
  { id: "verify", label: "Verification queue" },
  { id: "milestones", label: "Held tranches" },
  { id: "procurement", label: "Procurement" },
  { id: "rounds", label: "Rounds" },
  { id: "refunds", label: "Refunds" },
  { id: "log", label: "Agent log" },
  { id: "trust", label: "Trust" },
] as const;
type Tab = (typeof tabs)[number]["id"];

export default async function AdminPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab: raw } = await searchParams;
  const tab: Tab = tabs.some((t) => t.id === raw) ? (raw as Tab) : "overview";
  const [data, globe, dash, projects, lb, categories, rounds] = await Promise.all([getAdminData(), getGlobePins(), getDashboard(), getProjects(), getLeaderboard(), getCategories(), listRounds()]);
  const status = await getAgentStatus().catch(() => null);
  const [chain, chainRows] = tab === "trust" ? await Promise.all([verifyAuditChain().catch(() => null), getAuditChain(100).catch(() => [])]) : [null, []];
  const procurement = await listProcurement().catch(() => []);
  const open = data.cases.filter((c) => c.status === "open");
  const rings = open.filter(hasRingGraph);
  const docs = tab === "verify" ? await Promise.all(data.queue.map(async (project) => ({ project, documents: await getProjectDocuments(project.id) }))) : [];
  const counts: Record<Tab, number> = {
    overview: 0,
    rounds: 0,
    refunds: 0,
    trust: 0,
    procurement: procurement.filter((p) => p.needs_approval || p.status === "failed").length,
    cases: data.cases.filter((c) => c.status === "open").length,
    verify: data.queue.length,
    milestones: data.milestones.length,
    log: data.audit.length,
  };

  return (
    <>
      <PageTitle title="Admin console" crumb="Admin" />
      <section className="section">
        <div className="container-k space-y-8">
          <p className="max-w-[70ch] text-lg leading-8">
            Agents read, check and explain; anything big or unclear waits here for a person. Every decision is logged
            with a reason.
          </p>

          {status ? <AgentSwitch status={status} /> : <p role="status" className="border border-line bg-white p-4 text-sm">Couldn&apos;t read the agent switch. The API may be waking up.</p>}

          {data.sampleReason && (
            <p className="border-l-4 border-accent bg-white p-3 text-sm text-ink">
              {data.sampleReason} Buttons don&apos;t change anything in sample mode.
            </p>
          )}

          <div className="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[220px_minmax(0,1fr)]">
          <nav aria-label="Admin sections" className="h-fit bg-ink p-2 lg:sticky lg:top-32">
            <ul className="flex gap-1 overflow-x-auto lg:flex-col">
              {tabs.map((t) => (
                <li key={t.id}>
                  <Link
                    href={t.id === "overview" ? "/admin" : `/admin?tab=${t.id}`}
                    aria-current={tab === t.id ? "page" : undefined}
                    className={`flex min-h-12 items-center justify-between gap-3 whitespace-nowrap px-4 text-sm font-medium ${tab === t.id ? "bg-accent text-ink" : "text-white hover:bg-white/10"}`}
                  >
                    {t.label}
                    {t.id !== "overview" && counts[t.id] > 0 && <span className={`tabular px-2 text-xs leading-6 ${tab === t.id ? "bg-ink text-white" : "bg-white/15"}`}>{counts[t.id]}</span>}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="min-w-0 space-y-6">
          {tab === "overview" && (
            <Overview data={data} dash={dash} projects={projects} lb={lb} categories={categories} globe={globe} />
          )}
          {tab === "rounds" && <RoundsPanel rounds={rounds} />}
          {tab === "refunds" && <RefundPanel />}
          {tab === "cases" && (
            <div className="space-y-3">
              <p>The Watchdog freezes a project&apos;s <strong>matching</strong> (never its donations) and opens a case. Clear a false alarm, or confirm it.</p>
              {rings.length > 0 && <CollusionCases cases={rings} />}
              <CasesGrid rows={open.filter((c) => !hasRingGraph(c))} />
            </div>
          )}
          {tab === "verify" && (
            <div className="space-y-3">
              <p>Projects are listed only after a person checks their registration and plan.</p>
              <VerificationGrid rows={data.queue} />
              {docs.length > 0 && (
                <section className="space-y-4 bg-white p-6">
                  <h2 className="text-xl">Documents sent with each application</h2>
                  {docs.map(({ project, documents }) => (
                    <div key={project.id} className="space-y-2 border-t border-line pt-3">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="font-medium text-ink">
                          {project.title} <span className="text-sm text-text">#{project.id}</span>
                        </p>
                        <OwnerTokenButton projectId={project.id} />
                      </div>
                      {documents.length === 0 ? (
                        <p className="text-sm">No documents yet.</p>
                      ) : (
                        <ul className="flex flex-wrap gap-2 text-sm">
                          {documents.map((d) => (
                            <li key={d.id}>
                              <a href={d.fileUrl} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-9 items-center gap-2 border border-line px-3 text-primary hover:border-primary">
                                <span className="font-bold uppercase tracking-wider text-ink">{d.kind}</span> open link ↗
                                {d.flags.length > 0 && <span className="bg-accent px-1.5 text-[10px] font-bold uppercase text-ink">{d.flags.join(", ")}</span>}
                              </a>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </section>
              )}
              <section className="space-y-2 bg-white p-6">
                <h2 className="text-xl">Owner token for any project</h2>
                <p className="text-sm">For seeded projects or a lost token. The project then uploads evidence at /projects/&lt;id&gt;/evidence.</p>
                <OwnerTokenButton withInput />
              </section>
            </div>
          )}
          {tab === "milestones" && (
            <div className="space-y-3">
              <p>The Milestone Agent holds a tranche when a receipt check fails or the amount is above the approval threshold.</p>
              <MilestonesGrid rows={data.milestones} />
            </div>
          )}
          {tab === "procurement" && <ProcurementPanel rows={procurement} />}
          {tab === "trust" && <TrustPanel initial={chain} rows={chainRows} />}
          {tab === "log" && (
            <div className="space-y-3">
              <p>Every agent and admin action, with the inputs it saw, the rule result and the reason.</p>
              <AuditGrid rows={data.audit} />
            </div>
          )}
          </div>
          </div>
        </div>
      </section>
    </>
  );
}
