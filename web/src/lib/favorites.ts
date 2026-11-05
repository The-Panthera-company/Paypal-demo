"use client";

import { useSyncExternalStore } from "react";

// Favourites live in this browser only (no accounts yet): a per-viewer convenience that can move
// to the API later. Every read and write is guarded: private windows or blocked storage just
// mean nothing is remembered. One shared store, so every heart and counter updates together.
const KEY = "cg:favorites";
const EVENT = "cg:favorites-changed";
const EMPTY: string[] = [];
let cache: string[] | null = null;

function read(): string[] {
  if (cache) return cache;
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    cache = Array.isArray(v) ? v.map(String) : [];
  } catch {
    cache = [];
  }
  return cache;
}

function write(ids: string[]) {
  cache = ids;
  try {
    localStorage.setItem(KEY, JSON.stringify(ids));
  } catch {
    /* storage unavailable: kept for this page view only */
  }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(cb: () => void) {
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) {
      cache = null;
      cb();
    }
  };
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", onStorage); // other tabs
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", onStorage);
  };
}

export function useFavorites() {
  const ids = useSyncExternalStore(subscribe, read, () => EMPTY);
  return {
    ids,
    has: (id: string) => ids.includes(id),
    toggle: (id: string) => {
      const now = read();
      const on = !now.includes(id);
      write(on ? [...now, id] : now.filter((x) => x !== id));
      return on;
    },
  };
}
