"use client";

// Bryntum Gantt (trial build, aliased as @bryntum/gantt in package.json; swap for the licensed package when
// Bryntum issues the hackathon licence). Loaded only in the browser via MilestoneTimeline.
import { BryntumGantt } from "@bryntum/gantt-react";
import { useEffect, useRef } from "react";
import "@bryntum/gantt/fontawesome/css/fontawesome.css";
import "@bryntum/gantt/fontawesome/css/solid.css";
import "@bryntum/gantt/gantt.css";
import "@bryntum/gantt/stockholm-light.css";
import type { Milestone } from "@/lib/types";

const DAY = 86_400_000;
const statusLabel: Record<Milestone["status"], string> = {
  open: "Not started",
  evidence_submitted: "Evidence being checked",
  held: "Held for an admin",
  released: "Released",
};
const statusDone: Record<Milestone["status"], number> = { open: 0, evidence_submitted: 70, held: 70, released: 100 };
const statusColour: Record<Milestone["status"], string> = { open: "gray", evidence_submitted: "teal", held: "orange", released: "green" };

export default function MilestoneGantt({ milestones }: { milestones: Milestone[] }) {
  const gantt = useRef<BryntumGantt>(null);
  // Fit the whole plan into the visible width once it has rendered
  useEffect(() => {
    const t = setTimeout(() => gantt.current?.instance?.zoomToFit({ leftMargin: 40, rightMargin: 40 }), 300);
    return () => clearTimeout(t);
  }, []);
  const sorted = [...milestones].sort((a, b) => a.seq - b.seq);
  const fmt = (m: Milestone) =>
    new Intl.NumberFormat(undefined, { style: "currency", currency: m.amount.currency, maximumFractionDigits: 0 }).format(m.amount.amount / 100);

  // Each tranche runs from the previous milestone's due date to its own (the first gets four weeks).
  const tasks = sorted.map((m, i) => {
    const end = new Date(m.dueDate as string);
    const prev = sorted[i - 1]?.dueDate;
    const start = prev ? new Date(prev) : new Date(end.getTime() - 28 * DAY);
    return {
      id: m.id,
      name: `${m.seq}. ${m.title}`,
      startDate: start,
      endDate: end > start ? end : new Date(start.getTime() + DAY),
      percentDone: statusDone[m.status],
      eventColor: statusColour[m.status],
      manuallyScheduled: true,
      amount: fmt(m),
      statusText: statusLabel[m.status],
    };
  });
  const first = tasks[0]?.startDate ?? new Date();
  const last = tasks.at(-1)?.endDate ?? new Date();

  return (
    <div className="border border-line" style={{ height: 110 + tasks.length * 48 }} aria-label="Milestone timeline">
      <BryntumGantt
        ref={gantt}
        readOnly
        subGridConfigs={{ locked: { width: 420 } }}
        rowHeight={48}
        barMargin={10}
        startDate={new Date(first.getTime() - 7 * DAY)}
        endDate={new Date(last.getTime() + 14 * DAY)}
        viewPreset="weekAndMonth"
        columns={[
          { type: "name", field: "name", text: "Milestone", width: 190 },
          { field: "amount", text: "Tranche", width: 90, align: "right" },
          { field: "statusText", text: "Status", width: 140 },
        ]}
        taskMenuFeature={false}
        taskEditFeature={false}
        cellMenuFeature={false}
        headerMenuFeature={false}
        dependenciesFeature={false}
        projectLinesFeature={false}
        timeRangesFeature={{ showCurrentTimeLine: true }}
        project={{ tasks, autoSetConstraints: false }}
      />
    </div>
  );
}
