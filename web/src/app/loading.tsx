// Shown at once on every navigation while the page's data loads (Render's free API can take a moment).
export default function Loading() {
  return (
    <div className="container-k mt-[140px] min-h-[50vh] pb-16" aria-busy="true" aria-label="Loading">
      <div className="mb-6 h-10 w-72 animate-pulse bg-line" />
      <div className="grid gap-[30px] sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="h-72 animate-pulse bg-line" />
        ))}
      </div>
    </div>
  );
}
