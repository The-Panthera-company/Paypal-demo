"use client";

// Error state for every page: say what happened and offer a way forward (heuristic H9).
export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-10 text-center">
      <p className="font-medium">We couldn&apos;t load this page.</p>
      <p className="mt-1 text-sm text-muted">Your connection may be slow, or our server is busy. Nothing was charged.</p>
      <button onClick={reset} className="mt-4 min-h-11 rounded-lg bg-primary px-5 text-sm font-medium text-white hover:bg-primary-hover">
        Try again
      </button>
    </div>
  );
}
