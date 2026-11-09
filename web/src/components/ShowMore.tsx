"use client";

import { Children, useState } from "react";

/** Phones: show the first `step` items and a button for the next batch (long lists are hard to scroll) */
export function ShowMore({ children, step = 12, noun = "projects", className = "" }: { children: React.ReactNode; step?: number; noun?: string; className?: string }) {
  const items = Children.toArray(children);
  const [shown, setShown] = useState(step);
  return (
    <>
      <div className={className}>{items.slice(0, shown)}</div>
      {items.length > shown && (
        <button type="button" onClick={() => setShown((n) => n + step)} className="mt-6 min-h-12 w-full border border-line bg-white px-4 font-medium text-ink hover:border-primary">
          Show more {noun} ({items.length - shown} left)
        </button>
      )}
    </>
  );
}
