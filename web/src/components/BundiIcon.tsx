// Bundi, the platform's AI: a small floating robot (propeller, round body, visor face, hover waves).
export function BundiIcon({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="14 0 92 112" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M44 8h32M60 8v10" />
      <path d="M30 58q-10 4-11 14M90 58q10-6 12-18" />
      <circle cx="60" cy="52" r="32" fill="#fffaf2" />
      <path d="M38 46q22-12 44 0v14q-22 12-44 0z" fill="#fffaf2" />
      <circle cx="51" cy="52" r="3.5" fill="currentColor" stroke="none" />
      <circle cx="69" cy="52" r="3.5" fill="currentColor" stroke="none" />
      <path d="M48 94q12 6 24 0M54 104q6 3 12 0" />
    </svg>
  );
}
