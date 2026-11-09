"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { pauseAgentsAction, resumeAgentsAction } from "@/app/admin/actions";
import { Confirm, notify } from "@/components/Status";
import type { AgentStatus } from "@/lib/admin";

// The global kill switch, always on top of the admin console. Paused = no agent route can move money.
export function AgentSwitch({ status }: { status: AgentStatus }) {
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, start] = useTransition();
  const since = status.since ? new Date(status.since).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : null;

  const act = (fn: () => Promise<{ ok: boolean; message: string }>) =>
    start(async () => {
      const r = await fn();
      notify(r.message, r.ok ? "success" : "error");
      setAsking(false);
      setReason("");
      router.refresh();
    });

  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-wrap items-center gap-4 p-4 ${status.paused ? "bg-cat-health text-white" : "border border-line bg-white text-ink"}`}
    >
      <span className={`size-3 shrink-0 ${status.paused ? "bg-accent" : "bg-growth motion-safe:animate-pulse"}`} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-bold">{status.paused ? "Agents paused — no money can move" : "Agents are running"}</p>
        {status.paused && (
          <p className="text-sm opacity-90">
            {status.reason ?? "No reason given"}
            {since && <> · since {since}</>}
            {status.updatedBy && <> · by {status.updatedBy}</>}
          </p>
        )}
        {status.sample && <p className="text-sm text-text">Sample mode: the switch isn&apos;t connected.</p>}
      </div>
      {status.paused ? (
        <button type="button" disabled={pending} onClick={() => act(() => resumeAgentsAction())} className="btn disabled:opacity-50">
          {pending ? "Resuming…" : "Resume"}
        </button>
      ) : (
        <button type="button" disabled={pending} onClick={() => setAsking(true)} className="min-h-12 bg-cat-health px-5 font-bold text-white disabled:opacity-50">
          Pause agents
        </button>
      )}
      <Confirm
        open={asking}
        danger
        title="Pause every agent?"
        confirmLabel={pending ? "Pausing…" : "Pause agents"}
        body={
          <div className="space-y-3">
            <p>The Giving, Milestone and Watchdog agents stop moving money at once. Donors can still give by hand.</p>
            <label className="flex flex-col gap-1 text-sm text-ink">
              Reason (optional, kept in the audit log)
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} maxLength={500} className="border border-line p-2" placeholder="e.g. Investigating a Watchdog alert" />
            </label>
          </div>
        }
        onConfirm={() => act(() => pauseAgentsAction(reason))}
        onCancel={() => setAsking(false)}
      />
    </div>
  );
}
