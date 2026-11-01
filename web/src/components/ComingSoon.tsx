export function ComingSoon({ title, issue }: { title: string; issue: number }) {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold">{title}</h1>
      <p className="opacity-70">Coming soon (issue #{issue}).</p>
    </div>
  );
}
