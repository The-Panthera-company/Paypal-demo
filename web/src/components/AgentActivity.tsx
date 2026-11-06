"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAgentActivity, type AgentActivity as Row } from "@/lib/agent-trace";

const DOT: Record<string, string> = { ok: "bg-growth", pending: "bg-accent", blocked: "bg-cat-health", error: "bg-cat-health" };
const ACTOR: Record<string, string> = { "giving-agent": "Giving Agent", "milestone-agent": "Milestone Agent", "watchdog-agent": "Watchdog", watchdog: "Watchdog", admin: "Admin", system: "System" };

// Live feed of what the agents did (GET /agents/activity). Polls every 2 s while the tab is
// visible, stops while hidden, new rows slide in. One request at a time.
export function AgentActivity({ initial = [], limit = 50 }: { initial?: Row[]; limit?: number }) {
  const [rows, setRows] = useState<Row[]>(initial);
  const [state, setState] = useState<"loading" | "ok" | "error">(initial.length ? "ok" : "loading");
  const seen = useRef(new Set(initial.map((r) => r.id)));
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const busy = useRef(false);

  const load = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      const data = await fetchAgentActivity(limit);
      const added = data.filter((r) => !seen.current.has(r.id)).map((r) => r.id);
      data.forEach((r) => seen.current.add(r.id));
      if (added.length) setFresh(new Set(added));
      setRows(data);
      setState("ok");
    } catch {
      setState((s) => (s === "ok" ? "ok" : "error")); // keep showing old rows on a blip
    } finally {
      busy.current = false;
    }
  }, [limit]);

  useEffect(() => {
    let t: ReturnType<typeof setInterval> | undefined;
    const start = () => {
      if (t || document.hidden) return;
      load();
      t = setInterval(load, 2000);
    };
    const stop = () => {
      if (t) clearInterval(t);
      t = undefined;
    };
    const onVis = () => (document.hidden ? stop() : start());
    start();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [load]);

  if (state === "loading")
    return (
      <div className="space-y-2" role="status" aria-label="Loading agent activity">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="h-10 animate-pulse bg-line/60 motion-reduce:animate-none" />
        ))}
      </div>
    );
  if (state === "error" && rows.length === 0)
    return (
      <div className="space-y-3 border-l-4 border-cat-health bg-white p-4 text-sm text-ink" role="alert">
        <p>Couldn&apos;t load the agent activity.</p>
        <button type="button" onClick={() => { setState("loading"); load(); }} className="btn btn-2 !min-h-10">
          Try again
        </button>
      </div>
    );
  if (rows.length === 0) return <p className="border border-dashed border-line bg-white p-4 text-sm">No agent runs yet. Seed a mandate or click Run now.</p>;

  return (
    <ol className="divide-y divide-line bg-white ring-1 ring-line" aria-live="polite">
      {rows.map((r) => (
        <li key={r.id} className={`flex gap-3 p-3 text-sm ${fresh.has(r.id) ? "motion-safe:animate-[showcase-in_.4s_ease-out] bg-accent/20" : ""}`}>
          <span className={`mt-1.5 size-2.5 shrink-0 ${DOT[r.status] ?? "bg-line"}`} aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-ink">{r.title}</p>
            <p className="text-xs text-text">
              {ACTOR[r.actor] ?? r.actor} · {new Date(r.at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              {r.rule && <> · rule <strong className="text-cat-health">{r.rule}</strong></>}
              {r.status !== "ok" && <> · {r.status}</>}
            </p>
          </div>
          {r.run_id && (
            <Link href={`/agents?run=${r.run_id}`} className="shrink-0 self-center text-xs font-bold uppercase tracking-wider text-primary hover:underline">
              Trace
            </Link>
          )}
          {!r.run_id && r.project_id && (
            <Link href={`/projects/${r.project_id}`} className="shrink-0 self-center text-xs text-primary hover:underline">
              Project
            </Link>
          )}
        </li>
      ))}
    </ol>
  );
}
