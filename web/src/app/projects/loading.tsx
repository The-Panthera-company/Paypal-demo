// Loading state: skeleton cards so the layout doesn't jump.
export default function Loading() {
  return (
    <div className="container-k mt-[140px] pb-16" aria-busy="true" aria-label="Loading projects">
      <div className="mb-8 h-40 animate-pulse bg-line" />
      <div className="grid gap-[30px] sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="h-[460px] animate-pulse bg-line" />
        ))}
      </div>
    </div>
  );
}
