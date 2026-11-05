import Link from "next/link";
import { getGlobePins } from "@/lib/globe";

import { AuditGrid, CasesGrid, MilestonesGrid, VerificationGrid } from "@/components/admin/AdminGrids";
import { PageTitle } from "@/components/PageTitle";
import { getAdminData } from "@/lib/admin";

export const dynamic = "force-dynamic";

const tabs = [
  { id: "cases", label: "Watchdog cases" },
  { id: "verify", label: "Verification queue" },
  { id: "milestones", label: "Held tranches" },
  { id: "log", label: "Agent log" },
] as const;
type Tab = (typeof tabs)[number]["id"];

export default async function AdminPage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab: raw } = await searchParams;
  const tab: Tab = tabs.some((t) => t.id === raw) ? (raw as Tab) : "cases";
  const [data, globe] = await Promise.all([getAdminData(), getGlobePins()]);
  const counts: Record<Tab, number> = {
    cases: data.cases.filter((c) => c.status === "open").length,
    verify: data.queue.length,
    milestones: data.milestones.length,
    log: data.audit.length,
  };

  return (
    <>
      <PageTitle title="Admin console" crumb="Admin" globe={globe} />
      <section className="section">
        <div className="container-k space-y-8">
          <p className="max-w-[70ch] text-lg leading-8">
            Agents read, check and explain; anything big or unclear waits here for a person. Every decision is logged
            with a reason.
          </p>

          {data.sampleReason && (
            <p className="border-l-4 border-accent bg-white p-3 text-sm text-ink">
              {data.sampleReason} Buttons don&apos;t change anything in sample mode.
            </p>
          )}

          <nav aria-label="Admin sections" className="flex flex-wrap bg-brand">
            {tabs.map((t) => (
              <Link
                key={t.id}
                href={`/admin?tab=${t.id}`}
                aria-current={tab === t.id ? "page" : undefined}
                className={`flex min-h-14 items-center gap-2 px-6 font-medium ${tab === t.id ? "bg-white text-ink" : "text-white hover:bg-brand-dark"}`}
              >
                {t.label}
                <span className={`tabular px-2 text-xs leading-6 ${tab === t.id ? "bg-brand text-white" : "bg-white/20 text-white"}`}>{counts[t.id]}</span>
              </Link>
            ))}
          </nav>

          {tab === "cases" && (
            <div className="space-y-3">
              <p>The Watchdog freezes a project&apos;s <strong>matching</strong> (never its donations) and opens a case. Clear a false alarm, or confirm it.</p>
              <CasesGrid rows={data.cases.filter((c) => c.status === "open")} />
            </div>
          )}
          {tab === "verify" && (
            <div className="space-y-3">
              <p>Projects are listed only after a person checks their registration and plan.</p>
              <VerificationGrid rows={data.queue} />
            </div>
          )}
          {tab === "milestones" && (
            <div className="space-y-3">
              <p>The Milestone Agent holds a tranche when a receipt check fails or the amount is above the approval threshold.</p>
              <MilestonesGrid rows={data.milestones} />
            </div>
          )}
          {tab === "log" && (
            <div className="space-y-3">
              <p>Every agent and admin action, with the inputs it saw, the rule result and the reason.</p>
              <AuditGrid rows={data.audit} />
            </div>
          )}
        </div>
      </section>
    </>
  );
}
