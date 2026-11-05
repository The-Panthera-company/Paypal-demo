// Line-art doodles (24x24, stroke only) for the WhatsApp-style wallpaper and avatar backgrounds.
// Themed on giving: causes, people, money, places, everyday things.
export const DOODLES: string[] = [
  "M12 20s-7-4.4-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.6-7 10-7 10z", // heart
  "M12 3c3.5 4.5 6 7.6 6 10.5a6 6 0 01-12 0C6 10.6 8.5 7.5 12 3z", // drop
  "M5 19C5 10 10 5 19 5c0 9-5 14-14 14zm0 0l7-7", // leaf
  "M4 5h6a2 2 0 012 2v12a2 2 0 00-2-2H4zm16 0h-6a2 2 0 00-2 2v12a2 2 0 012-2h6z", // book
  "M12 3l2.6 5.6 6 .7-4.5 4 1.3 6L12 16.4 6.6 19.3l1.3-6-4.5-4 6-.7z", // star
  "M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5", // sun
  "M12 3a9 9 0 100 18 9 9 0 000-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18", // globe
  "M12 4a8 8 0 100 16 8 8 0 000-16zM14.5 9.5c-.5-1-1.5-1.5-2.5-1.5-1.4 0-2.5.8-2.5 2s1.1 1.6 2.5 2 2.5.8 2.5 2-1.1 2-2.5 2c-1 0-2-.5-2.5-1.5M12 6.5v11", // coin
  "M4 11l8-7 8 7v9H4zM10 20v-5h4v5", // house
  "M12 3l5 7h-3l4 6H6l4-6H7zM12 16v5", // tree
  "M4 20l1-4L16 5l3 3L8 19zM14 7l3 3", // pencil
  "M4 5h16v10H9l-5 4z", // chat bubble
  "M4 8h4l2-2h4l2 2h4v11H4zM12 10a3 3 0 100 6 3 3 0 000-6z", // camera
  "M5 8h11v6a5 5 0 01-5 5h-1a5 5 0 01-5-5zM16 10h2a2 2 0 010 4h-2M8 3v2M11 3v2", // cup
  "M9 18V6l10-2v12M9 18a2 2 0 11-4 0 2 2 0 014 0zM19 16a2 2 0 11-4 0 2 2 0 014 0", // music
  "M12 3a9 9 0 100 18 9 9 0 000-18zM8.5 14a4 4 0 007 0M9 9.5h.01M15 9.5h.01", // smile
  "M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z", // medical cross
  "M4 10h16v10H4zM3 7h18v3H3zM12 7v13M12 7c-2-4-6-3-5 0M12 7c2-4 6-3 5 0", // gift
  "M12 21s7-6.5 7-12a7 7 0 00-14 0c0 5.5 7 12 7 12zM12 6a3 3 0 100 6 3 3 0 000-6z", // map pin
  "M6 17a3 3 0 100-6 3 3 0 000 6zM18 17a3 3 0 100-6 3 3 0 000 6zM6 14l4-6h5l3 6M10 8l2 6h-6", // bicycle
  "M7 11V7a5 5 0 0110 0v4M5 11h14v9H5z", // padlock (safe payments)
  "M3 20h18M5 20V10l7-5 7 5v10M9 20v-6h6v6", // school
  "M8 3h8M9 3v5l-4 9a2 2 0 002 3h10a2 2 0 002-3l-4-9V3", // flask (STEM)
  "M2 12c3-4 6-4 10 0s7 4 10 0", // wave
  "M12 2v4M12 18v4M2 12h4M18 12h4", // sparkle
  "M7 12a5 5 0 1010 0 5 5 0 00-10 0zM3 21c1.5-3.5 5-5 9-5s7.5 1.5 9 5", // person
  // little avatar faces, like the characters in the anonymous avatars
  "M6 9L5 3l4 3h6l4-3-1 6c2 5-1 11-6 11S4 14 6 9zM9.5 12h.01M14.5 12h.01M11 15l1 1 1-1", // cat
  "M12 6a8 8 0 110 16 8 8 0 010-16zM6 5a3 3 0 110 6M18 5a3 3 0 100 6M10 12h.01M14 12h.01M10 17q2 2 4 0", // bear
  "M6 7h12v11H6zM12 7V4M9.5 11h1M13.5 11h1M10 15h4M4 11v3M20 11v3", // robot
  "M6 6q6-4 12 0v10q-6 7-12 0zM9.5 10a2 2 0 110 4 2 2 0 010-4zM14.5 10a2 2 0 110 4 2 2 0 010-4zM11 16l1 1.5 1-1.5", // owl
];

/** Deterministic pseudo-random numbers from a seed (mulberry32) */
export function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * A seamless wallpaper tile, WhatsApp-style: doodles on a jittered grid, random turns and sizes,
 * small circles in the gaps. Returns an SVG string (use as a CSS background via `doodleUrl`).
 */
export function doodleTile({ stroke, size = 320, seed = 7, density = 6 }: { stroke: string; size?: number; seed?: number; density?: number }) {
  const r = rng(seed);
  const cell = size / density;
  const parts: string[] = [];
  for (let gy = 0; gy < density; gy++)
    for (let gx = 0; gx < density; gx++) {
      const d = DOODLES[Math.floor(r() * DOODLES.length)];
      const s = 0.8 + r() * 0.5;
      const x = gx * cell + r() * (cell - 24 * s);
      const y = gy * cell + r() * (cell - 24 * s);
      parts.push(`<path d="${d}" transform="translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${Math.round(r() * 60 - 30)} 12 12) scale(${s.toFixed(2)})"/>`);
      // filler circles in the gaps, like the reference
      if (r() > 0.4) parts.push(`<circle cx="${(gx * cell + r() * cell).toFixed(1)}" cy="${(gy * cell + r() * cell).toFixed(1)}" r="${(1 + r() * 1.5).toFixed(1)}"/>`);
    }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"><g fill="none" stroke="${stroke}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">${parts.join("")}</g></svg>`;
}

export const doodleUrl = (svg: string) => `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
