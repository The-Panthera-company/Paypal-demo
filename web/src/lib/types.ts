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

/** A milestone update with evidence (photo or receipt), shown in the impact gallery and story feed */
export type ImpactUpdate = {
  id: string;
  projectId: string;
  title: string;
  caption: string;
  kind: "photo" | "receipt";
  date: string;
  tranche?: Money;
};

/** A backer's own words about a project they supported (shown only with their consent) */
export type BackerStory = {
  id: string;
  quote: string;
  name: string;
  role: string;
  projectId: string;
};

export type Sponsor = { id: string; name: string; pool: Money };

/** One row of the matching leaderboard (GET /rounds/{id}/leaderboard) */
export type LeaderboardRow = {
  rank: number;
  projectId: string;
  title: string;
  categoryId: string;
  backerCount: number;
  raised: Money;
  score: number;
  floor: Money;
  crowd: Money;
  match: Money;
  capped: boolean;
  frozen: boolean;
};

export type Leaderboard = {
  roundId: string;
  roundName: string;
  endsAt: string;
  pool: Money;
  isFinal: boolean;
  computedAt: string;
  rows: LeaderboardRow[];
  /** true when built from local sample data, not the API */
  sample: boolean;
};
