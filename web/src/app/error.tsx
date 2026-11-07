"use client";

import { useRouter } from "next/navigation";
import { startTransition, useCallback, useEffect, useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const TRIES = 5; // about a minute: Render's free plan can take ~50 s to wake a sleeping service
const WAIT = 12;

// Error state for every page. The usual cause on the hosted demo is the free server waking up
// after 15 idle minutes, so: wake the API, then retry by itself a few times before asking.
export default function Error({ reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  const [tries, setTries] = useState(0);
  const [left, setLeft] = useState(WAIT);
  const auto = tries < TRIES;
  const woke = useRef(false);

  const retry = useCallback(() => {
    // Re-run the page's server code and re-render (the documented pattern for server errors)
    startTransition(() => {
      router.refresh();
      reset();
    });
  }, [router, reset]);

  useEffect(() => {
    if (!woke.current && API_URL) {
      woke.current = true;
      fetch(`${API_URL}/health`, { mode: "no-cors" }).catch(() => undefined); // start waking it now
    }
    if (!auto) return;
    setLeft(WAIT);
    const tick = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    const go = setTimeout(() => {
      setTries((t) => t + 1);
      retry();
    }, WAIT * 1000);
    return () => {
      clearInterval(tick);
      clearTimeout(go);
    };
  }, [auto, tries, retry]);

  return (
    <div className="container-k mt-[140px] pb-16">
      <div className="border border-line bg-white p-10 text-center" role="status">
        {auto ? (
          <>
            <span className="mx-auto mb-4 block size-3 animate-ping bg-primary motion-reduce:animate-none" aria-hidden />
            <p className="font-display text-2xl text-ink">Waking up the server…</p>
            <p className="mt-2 max-w-xl mx-auto">
              The demo runs on free hosting that sleeps when nobody has visited for a while. It takes up to a minute to wake. Trying again in <span className="tabular font-bold text-ink">{left}</span> s
              {tries > 0 && <> (attempt {tries + 1} of {TRIES + 1})</>}. Nothing was charged.
            </p>
            <button
              onClick={() => {
                setTries((t) => t + 1);
                retry();
              }}
              className="btn btn-2 mt-6"
            >
              Try now
            </button>
          </>
        ) : (
          <>
            <p className="font-display text-2xl text-ink">We couldn&apos;t load this page</p>
            <p className="mt-2">Your connection may be slow, or our server is busy. Nothing was charged.</p>
            <button
              onClick={() => {
                setTries(0);
                retry();
              }}
              className="btn btn-2 mt-6"
            >
              Try again
            </button>
          </>
        )}
      </div>
    </div>
  );
}
