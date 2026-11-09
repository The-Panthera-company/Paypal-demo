// A donor–project graph for a collusion ring. Plain SVG, no layout library: donors in a left column,
// projects in a right column, both in a fixed order (cluster first, then by id), so the same evidence
// always draws the same picture. Donors are only ever shown as "Donor <id>", never by name.

export type GraphNode = { id: number | string; type: string; label: string };
export type GraphEdge = { source: number | string; target: number | string; weight: number };
export type Graph = { nodes?: GraphNode[]; edges?: GraphEdge[] };

export type RingMetrics = { donors: number; projects: number; shared: number; ratio: number; total: number };

/** Collusion cases whose evidence carries a graph. Everything else stays in the cases table. */
export function hasRingGraph(c: { rule: string; evidence: Record<string, unknown> | null }) {
  const g = c.evidence?.graph as Graph | undefined;
  return c.rule === "collusion_cluster" && !!g && Array.isArray(g.nodes) && g.nodes.length > 0;
}

const isDonor = (n: GraphNode) => n.type.toLowerCase() === "donor";
const donorLabel = (n: GraphNode) => (/^donor\b/i.test(n.label) ? n.label : `Donor ${n.id}`);
const cmp = (a: GraphNode, b: GraphNode) => String(a.id).localeCompare(String(b.id), undefined, { numeric: true });

export function analyseRing(graph: Graph, clusterIds: (number | string)[]) {
  const nodes = graph.nodes ?? [];
  const edges = (graph.edges ?? []).filter((e) => Number.isFinite(e.weight));
  const cluster = new Set(clusterIds.map(String));
  const donors = nodes.filter(isDonor);
  const projects = nodes.filter((n) => !isDonor(n));
  const ringEdges = edges.filter((e) => cluster.has(String(e.source)));
  const backers = new Map<string, Set<string>>();
  for (const e of ringEdges) backers.set(String(e.target), (backers.get(String(e.target)) ?? new Set()).add(String(e.source)));
  const ringProjects = new Set(backers.keys());
  const shared = [...backers.values()].filter((s) => s.size >= 2).length;
  const metrics: RingMetrics = {
    donors: donors.filter((d) => cluster.has(String(d.id))).length || cluster.size,
    projects: ringProjects.size,
    shared,
    ratio: ringProjects.size ? shared / ringProjects.size : 0,
    total: ringEdges.reduce((s, e) => s + e.weight, 0),
  };
  const order = (list: GraphNode[], hot: (n: GraphNode) => boolean) => [...list].sort((a, b) => Number(hot(b)) - Number(hot(a)) || cmp(a, b));
  return {
    donors: order(donors, (d) => cluster.has(String(d.id))),
    projects: order(projects, (p) => ringProjects.has(String(p.id))),
    edges,
    cluster,
    ringProjects,
    metrics,
  };
}

export function CollusionGraph({ graph, clusterIds, title = "Donor–project graph" }: { graph: Graph; clusterIds: (number | string)[]; title?: string }) {
  const { donors, projects, edges, cluster, ringProjects, metrics } = analyseRing(graph, clusterIds);
  const ROW = 34;
  const W = 640;
  const H = Math.max(donors.length, projects.length, 3) * ROW + 40;
  const y = (i: number, n: number) => 20 + (H - 40) * ((i + 0.5) / Math.max(n, 1));
  const dY = new Map(donors.map((d, i) => [String(d.id), y(i, donors.length)]));
  const pY = new Map(projects.map((p, i) => [String(p.id), y(i, projects.length)]));
  const max = Math.max(1, ...edges.map((e) => e.weight));
  const DX = 150;
  const PX = W - 230;
  const label = `${title}: ${metrics.donors} flagged donors backing ${metrics.projects} projects, ${metrics.shared} of them shared by two or more flagged donors.`;

  return (
    <figure className="space-y-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full bg-white" role="img" aria-label={label}>
        {edges.map((e, i) => {
          const a = dY.get(String(e.source));
          const b = pY.get(String(e.target));
          if (a === undefined || b === undefined) return null;
          const hot = cluster.has(String(e.source));
          return (
            <line key={i} x1={DX} y1={a} x2={PX} y2={b} stroke={hot ? "var(--color-cat-health)" : "var(--color-line)"} strokeOpacity={hot ? 0.85 : 0.6} strokeWidth={1.5 + (e.weight / max) * 6.5} strokeLinecap="round" />
          );
        })}
        {donors.map((d) => {
          const hot = cluster.has(String(d.id));
          const cy = dY.get(String(d.id))!;
          return (
            <g key={`d${d.id}`} opacity={hot ? 1 : 0.4}>
              <rect x={DX - 7} y={cy - 7} width={14} height={14} fill={hot ? "var(--color-cat-health)" : "var(--color-outline)"} />
              <text x={DX - 14} y={cy + 4} textAnchor="end" fontSize="13" fill="var(--color-ink)" fontWeight={hot ? 700 : 400}>
                {donorLabel(d)}
              </text>
            </g>
          );
        })}
        {projects.map((p) => {
          const hot = ringProjects.has(String(p.id));
          const cy = pY.get(String(p.id))!;
          const t = p.label.length > 28 ? `${p.label.slice(0, 27)}…` : p.label;
          return (
            <g key={`p${p.id}`} opacity={hot ? 1 : 0.4}>
              <circle cx={PX} cy={cy} r={8} fill={hot ? "var(--color-primary)" : "var(--color-outline)"} />
              <text x={PX + 14} y={cy + 4} fontSize="13" fill="var(--color-ink)" fontWeight={hot ? 700 : 400}>
                {t}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-text">
        <span className="inline-flex items-center gap-1.5"><span className="size-3 bg-cat-health" aria-hidden /> Flagged donor</span>
        <span className="inline-flex items-center gap-1.5"><span className="size-3 rounded-full bg-primary" aria-hidden /> Project they back</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-1 w-6 bg-cat-health" aria-hidden /> Thicker line = more given</span>
        <span className="inline-flex items-center gap-1.5"><span className="size-3 bg-outline opacity-40" aria-hidden /> Not in the ring (dimmed)</span>
      </figcaption>
      <details className="bg-white p-3 text-sm">
        <summary className="cursor-pointer font-medium text-ink">The graph as a table</summary>
        <table className="mt-2 w-full text-left">
          <caption className="sr-only">Every donation link in the graph</caption>
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="py-1">Donor</th>
              <th scope="col" className="py-1">Project</th>
              <th scope="col" className="py-1 text-right">Weight</th>
              <th scope="col" className="py-1">In the ring</th>
            </tr>
          </thead>
          <tbody>
            {edges.map((e, i) => {
              const d = donors.find((n) => String(n.id) === String(e.source));
              const p = projects.find((n) => String(n.id) === String(e.target));
              return (
                <tr key={i} className="border-b border-line/60">
                  <td className="py-1">{d ? donorLabel(d) : `Donor ${e.source}`}</td>
                  <td className="py-1">{p?.label ?? `Project ${e.target}`}</td>
                  <td className="tabular py-1 text-right">{e.weight.toLocaleString()}</td>
                  <td className="py-1">{cluster.has(String(e.source)) ? "Yes" : "No"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
