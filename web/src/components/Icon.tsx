// One line-icon set (Lucide-style, 24 px grid, 1.6 stroke) drawn inline so it adds no package.
const paths: Record<string, React.ReactNode> = {
  heart: <path d="M12 21s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.5-7 10-7 10z" />,
  education: (
    <>
      <path d="M2 8l10-4 10 4-10 4z" />
      <path d="M6 10v5c3 2 9 2 12 0v-5" />
    </>
  ),
  leaf: (
    <>
      <path d="M12 22V11" />
      <path d="M12 11C12 6 8 3 4 3c0 5 3 8 8 8z" />
      <path d="M12 14c0-4 3-7 8-7 0 4-3 7-8 7z" />
    </>
  ),
  drop: <path d="M12 3s6 7 6 11a6 6 0 0 1-12 0c0-4 6-11 6-11z" />,
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5" />
      <path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c1.8.7 3 2.5 3.5 5.2" />
    </>
  ),
  project: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="1" />
      <path d="M3 9h18M8 13h8M8 16h5" />
    </>
  ),
  card: (
    <>
      <rect x="2.5" y="5" width="19" height="14" rx="1.5" />
      <path d="M2.5 10h19M6 15h4" />
    </>
  ),
  hand: (
    <>
      <path d="M3 14h3l4 3h5a2 2 0 0 0 0-4h-4" />
      <path d="M6 14v6M10 17l7.5-1.8a2 2 0 0 1 2.4 1.5l-9.9 3.3H6" />
      <circle cx="15" cy="6" r="3" />
    </>
  ),
  scale: (
    <>
      <path d="M12 3v18M5 21h14M5 7h14" />
      <path d="M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z" />
    </>
  ),
  receipt: (
    <>
      <path d="M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2z" />
      <path d="M9 8h6M9 12h6M9 16h3" />
    </>
  ),
  chat: <path d="M4 5h16v11H9l-5 4z" />,
};

export function Icon({ name, size = 32, className = "" }: { name: keyof typeof paths | string; size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {paths[name] ?? paths.heart}
    </svg>
  );
}

export const categoryIcon: Record<string, string> = { health: "heart", education: "education", environment: "leaf", water: "drop" };
