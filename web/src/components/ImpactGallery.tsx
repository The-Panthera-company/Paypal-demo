"use client";

import { useRef, useState } from "react";
import type { ImpactUpdate, Project } from "@/lib/types";
import { CategoryArt } from "./ui";

type Item = ImpactUpdate & { project?: Pick<Project, "title" | "categoryId"> };

// Krowd gallery, repurposed: every tile is milestone evidence. Opens in a native <dialog>
// lightbox (Esc and focus handling come from the browser).
export function ImpactGallery({ items, dateLabels }: { items: Item[]; dateLabels: Record<string, string> }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [active, setActive] = useState<Item | null>(null);

  const open = (item: Item) => {
    setActive(item);
    dialog.current?.showModal();
  };

  return (
    <>
      <ul className="grid gap-[30px] sm:grid-cols-2 lg:grid-cols-3">
        {items.map((u) => (
          <li key={u.id}>
            <button type="button" onClick={() => open(u)} className="group block w-full text-left">
              <div className="relative aspect-[4/3] overflow-hidden">
                <div className="size-full transition-transform duration-300 group-hover:scale-110">
                  <CategoryArt id={u.project?.categoryId ?? "education"} seed={u.id} label={u.title} />
                </div>
                <span className="absolute left-4 top-4 bg-white px-3 text-xs font-bold uppercase leading-7 tracking-[2px] text-ink">
                  {u.kind === "receipt" ? "Receipt" : "Photo"}
                </span>
                <span className="corner absolute inset-x-0 bottom-0 bg-ink/80 p-4 text-white" style={{ ["--corner-size" as string]: "12px" }}>
                  <span className="block font-display text-lg">{u.title}</span>
                  <span className="text-sm text-brand-tint">{u.project?.title}</span>
                </span>
              </div>
            </button>
          </li>
        ))}
      </ul>

      <dialog
        ref={dialog}
        onClose={() => setActive(null)}
        className="m-auto w-[min(900px,92vw)] bg-white p-0 backdrop:bg-ink/80"
        aria-label={active?.title}
      >
        {active && (
          <div className="grid md:grid-cols-[1.4fr_1fr]">
            <div className="aspect-[4/3]">
              <CategoryArt id={active.project?.categoryId ?? "education"} seed={active.id} label={active.title} />
            </div>
            <div className="space-y-3 p-6">
              <p className="tag">{active.kind}</p>
              <h3 className="text-2xl">{active.title}</h3>
              <p className="text-sm text-ink">{active.project?.title}</p>
              <p>{active.caption}</p>
              <p className="text-sm">{dateLabels[active.id]}</p>
              <form method="dialog">
                <button className="btn btn-2 mt-2 w-full">Close</button>
              </form>
            </div>
          </div>
        )}
      </dialog>
    </>
  );
}
