"use client";

import { useEffect, useState } from "react";

const parts = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return [
    { v: Math.floor(s / 86400), l: "Days" },
    { v: Math.floor((s % 86400) / 3600), l: "Hours" },
    { v: Math.floor((s % 3600) / 60), l: "Minutes" },
    { v: s % 60, l: "Seconds" },
  ];
};

// Time left in the matching round (from the round's end date). Screen readers get one sentence,
// not a number that changes every second.
export function Countdown({ endsAt, label = "Matching round closes in", small = false }: { endsAt: string; label?: string; small?: boolean }) {
  const end = new Date(endsAt).getTime();
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const p = parts(end - (now ?? end));
  const days = Math.ceil((end - Date.now()) / 86_400_000);

  return (
    <div>
      <p className={`mb-3 font-medium ${small ? "text-sm text-ink" : "text-white"}`}>{label}</p>
      <p className="sr-only">
        {label} about {days} days.
      </p>
      <div className="flex gap-2 sm:gap-3" aria-hidden>
        {p.map(({ v, l }) => (
          <div key={l} className="text-center">
            <span
              className={`tabular block rounded-md bg-cobalt-green font-bold text-ink ${
                small ? "w-14 py-2 text-2xl" : "w-16 py-3 text-3xl sm:w-20 sm:py-5 sm:text-[42px]"
              }`}
            >
              {now === null ? "--" : String(v).padStart(2, "0")}
            </span>
            <span className={`mt-2 block text-[11px] font-bold uppercase tracking-wider ${small ? "text-ink" : "text-white"}`}>{l}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
