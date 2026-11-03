"use client";

// Error state for every page: say what happened and offer a way forward.
export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="container-k mt-[140px] pb-16">
      <div className="border border-line bg-white p-10 text-center">
        <p className="font-display text-2xl text-ink">We couldn&apos;t load this page</p>
        <p className="mt-2">Your connection may be slow, or our server is busy. Nothing was charged.</p>
        <button onClick={reset} className="btn mt-6">
          Try again
        </button>
      </div>
    </div>
  );
}
