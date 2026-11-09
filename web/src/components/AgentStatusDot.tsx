"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

// Small dot in the top nav: visible from every page when the agent kill switch is on.
export function AgentStatusDot() {
  const pathname = usePathname();
  const [paused, setPaused] = useState<boolean | null>(null);
  useEffect(() => {
    let stop = false;
    const load = () => {
      if (document.hidden) return;
      fetch("/api/agent-status", { cache: "no-store" })
        .then((r) => r.json())
        .then((s: { paused: boolean; known: boolean }) => {
          if (!stop) setPaused(s.known ? s.paused : null);
        })
        .catch(() => undefined);
    };
    load();
    const t = setInterval(load, 30_000);
    document.addEventListener("visibilitychange", load);
    return () => {
      stop = true;
      clearInterval(t);
      document.removeEventListener("visibilitychange", load);
    };
  }, [pathname]);
  if (paused === null) return null;
  return (
    <Link href="/agents" className="inline-flex items-center gap-2 text-sm text-white hover:text-accent" title={paused ? "Agents paused: no money can move" : "Agents are running"}>
      <span className={`size-2.5 ${paused ? "bg-cat-health ring-2 ring-accent" : "bg-cobalt-green"}`} aria-hidden />
      <span className={paused ? "font-bold" : "sr-only"}>{paused ? "Agents paused" : "Agents are running"}</span>
    </Link>
  );
}
