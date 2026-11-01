// Loading state: card-shaped placeholders so the layout doesn't jump.
export default function Loading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading projects">
      <div className="h-9 w-48 animate-pulse rounded bg-line" />
      <div className="h-32 animate-pulse rounded-xl bg-line" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="h-56 animate-pulse rounded-xl bg-line" />
        ))}
      </div>
    </div>
  );
}
