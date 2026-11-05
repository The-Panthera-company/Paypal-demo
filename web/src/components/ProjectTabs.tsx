"use client";

import { useRef, useState } from "react";

// Tabs for the project page (Story / Updates / Team). Panels are rendered on the server and passed
// in; all stay in the HTML (hidden ones with `hidden`), so search and no-JS readers get everything.
export function ProjectTabs({ tabs }: { tabs: { id: string; label: string; badge?: string; content: React.ReactNode }[] }) {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: React.KeyboardEvent) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    const n = (active + d + tabs.length) % tabs.length;
    setActive(n);
    refs.current[n]?.focus();
  };
  return (
    <div>
      <div className="flex flex-wrap bg-brand" role="tablist" aria-label="Project sections" onKeyDown={onKey}>
        {tabs.map((t, i) => (
          <button
            key={t.id}
            ref={(b) => {
              refs.current[i] = b;
            }}
            role="tab"
            id={`ptab-${t.id}`}
            aria-selected={i === active}
            aria-controls={`ppanel-${t.id}`}
            tabIndex={i === active ? 0 : -1}
            onClick={() => setActive(i)}
            className={`flex min-h-[64px] items-center gap-2 px-6 text-lg font-medium sm:px-8 ${i === active ? "bg-white text-ink" : "text-white hover:bg-white/10"}`}
          >
            {t.label}
            {t.badge && <span className={`px-1.5 text-xs leading-5 ${i === active ? "bg-primary text-white" : "bg-white/20"}`}>{t.badge}</span>}
          </button>
        ))}
      </div>
      {tabs.map((t, i) => (
        <div key={t.id} role="tabpanel" id={`ppanel-${t.id}`} aria-labelledby={`ptab-${t.id}`} hidden={i !== active} className="pt-10">
          {t.content}
        </div>
      ))}
    </div>
  );
}
