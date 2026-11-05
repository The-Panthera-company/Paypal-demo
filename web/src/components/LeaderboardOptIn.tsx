"use client";

import { useState } from "react";
import { notify } from "./Status";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

// Privacy is opt-in (design doc): donors are anonymous unless they switch this on. PATCH /donors/{id}.
export function LeaderboardOptIn({ donorId, initial, sample }: { donorId: string; initial: boolean; sample: boolean }) {
  const [on, setOn] = useState(initial);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    const next = !on;
    if (sample || !API_URL) {
      setOn(next);
      notify("Sample mode: nothing saved.", "info");
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(`${API_URL}/donors/${donorId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ show_on_leaderboard: next }),
      });
      if (!r.ok) throw new Error();
      setOn(next);
      notify(next ? "Your name can now appear on public pages." : "You're anonymous again.", "success");
    } catch {
      notify("Couldn't save. Check your connection and try again.", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        role="switch"
        aria-checked={on}
        onClick={toggle}
        disabled={busy}
        className="flex min-h-12 items-center gap-3 text-left text-ink disabled:opacity-60"
      >
        <span className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${on ? "bg-primary" : "bg-outline"}`} aria-hidden>
          <span className={`absolute top-1 size-5 rounded-full bg-white transition-all ${on ? "left-6" : "left-1"}`} />
        </span>
        <span>
          <span className="block font-medium">Show my name on the leaderboard</span>
          <span className="text-sm text-text">Off by default. Public pages only ever show how many people backed a project.</span>
        </span>
      </button>
    </div>
  );
}
