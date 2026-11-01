// Shapes the frontend expects from the core API (Person 1).
// Replace with types generated from /openapi.json once the spec exists (issue #5).

/** Amounts are integers in minor units (cents); 12345 = 123.45 */
export type Money = { amount: number; currency: string };

export type Category = {
  id: string;
  name: string;
  projectCount: number;
  raised: Money;
};

export type ProjectStatus = "verified" | "active" | "frozen" | "completed";

export type Project = {
  id: string;
  title: string;
  categoryId: string;
  facilitator: string;
  summary: string;
  facets: { cause: string; group: string; region: string };
  tags: string[];
  goal: Money;
  raised: Money;
  backerCount: number;
  urgency: 1 | 2 | 3 | 4 | 5;
  status: ProjectStatus;
  /** ISO date the current round of funding ends */
  endsAt: string;
};

export type ProjectFilters = {
  category?: string;
  cause?: string;
  group?: string;
  region?: string;
  q?: string;
};
