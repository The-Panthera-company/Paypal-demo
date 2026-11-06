"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import { runAgentNow } from "@/app/agents/actions";
import { fetchAgentRun, fetchAgentRuns, type AgentRun } from "@/lib/agent-trace";
import { AgentTrace, TraceSkeleton } from "./AgentTrace";
import { Banner, notify } from "./Status";

// Shows one run's trace (a given id, or the latest), with Run now. Used on /agents (full) and in
// the Giving Agent's last step (compact, with a link to the full trace).
export function AgentRunViewer({ runId, initial, compact = false, showRunNow = true }: { runId?: number; initial?: AgentRun | null; compact?: boolean; showRunNow?: boolean }) {
  const [run, setRun] = useState<AgentRun | null>(initial ?? null);
  const [state, setState] = useState<"loading" | "ok" | "empty" | "error">(initial ? "ok" : "loading");
  const [animate, setAnimate] = useState(false);
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async (id?: number, anim = false) => {
    setState("loading");
    try {
      const r = id ? await fetchAgentRun(id) : (await fetchAgentRuns(1))[0];
      setRun(r ?? null);
      setAnimate(anim);
      setState(r ? "ok" : "empty");
    } catch {
      setState("error");
    }
  }, []);

  useEffect(() => {
    if (!initial) load(runId);
  }, [initial, runId, load]);

  const runNow = () =>
    start(async () => {
      setMsg(null);
      const r = await runAgentNow();
      setMsg({ ok: r.ok, text: r.message });
      notify(r.message, r.ok ? "success" : "error");
      if (r.ok) await load(r.runId ?? undefined, true); // replay the new trace step by step
    });

  return (
    <div className="space-y-4">
      {showRunNow && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm">
            {run ? (
              <>
                Run #{run.id} · {new Date(run.run_at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
              </>
            ) : (
              "No run shown yet."
            )}
          </p>
          <button type="button" onClick={runNow} disabled={pending} className="btn !min-h-11 disabled:opacity-60">
            {pending ? "Running…" : "Run now"}
          </button>
        </div>
      )}
      {pending && (
        <p role="status" className="flex items-center gap-2 text-sm text-ink">
          <span className="size-2 animate-ping bg-primary motion-reduce:animate-none" aria-hidden /> The agent is reading projects, scoring them and asking the rules engine…
        </p>
      )}
      {msg && <Banner tone={msg.ok ? "success" : "error"}>{msg.text}</Banner>}

      {state === "loading" && <TraceSkeleton />}
      {state === "error" && (
        <div className="space-y-3 border-l-4 border-cat-health bg-white p-4 text-sm text-ink" role="alert">
          <p>Couldn&apos;t load the agent trace.</p>
          <button type="button" onClick={() => load(runId)} className="btn btn-2 !min-h-10">
            Try again
          </button>
        </div>
      )}
      {state === "empty" && <p className="border border-dashed border-line bg-white p-4 text-sm">No agent runs yet. Seed a mandate or click Run now.</p>}
      {state === "ok" && run && <AgentTrace run={run} animate={animate} compact={compact} />}
    </div>
  );
}
