// Local sample data so pages render before the Postman mock and Person 3's seed JSON exist.
// The platform is not tied to one country: projects carry their own region and currency.
import type { BackerStory, Category, ImpactUpdate, Project, Sponsor } from "./types";

const usd = (amount: number) => ({ amount: amount * 100, currency: "USD" });

export const categories: Category[] = [
  { id: "health", name: "Health", projectCount: 2, raised: usd(1_690) },
  { id: "education", name: "Education", projectCount: 4, raised: usd(1_025) },
  { id: "environment", name: "Environment", projectCount: 1, raised: usd(920) },
  { id: "water", name: "Water", projectCount: 1, raised: usd(430) },
];

const inDays = (n: number) => new Date(Date.now() + n * 86_400_000).toISOString();

export const projects: Project[] = [
  {
    id: "lanet-library",
    title: "Lanet Library",
    categoryId: "education",
    facilitator: "Lanet Community Group",
    summary: "Books and shelving for a community library used by three primary schools.",
    facets: { cause: "Books & learning", group: "Children", region: "East Africa" },
    tags: ["primary school", "literacy"],
    goal: usd(6_000),
    raised: usd(400),
    backerCount: 16,
    urgency: 2,
    status: "active",
    endsAt: inDays(20),
    milestones: [
      { id: "m1", seq: 1, title: "Buy 120 books", amount: usd(1_500), match: usd(400), dueDate: inDays(-20), status: "released" },
      { id: "m2", seq: 2, title: "Build shelving", amount: usd(2_000), match: usd(500), dueDate: inDays(5), status: "evidence_submitted" },
      { id: "m3", seq: 3, title: "Reading programme, first term", amount: usd(2_500), match: usd(600), dueDate: inDays(40), status: "open" },
    ],
  },
  {
    id: "kaptembwo-desks",
    title: "Kaptembwo Desks",
    categoryId: "education",
    facilitator: "Kaptembwo Parents Association",
    summary: "Forty desks so pupils no longer sit on the floor.",
    facets: { cause: "Classrooms", group: "Children", region: "East Africa" },
    tags: ["primary school"],
    goal: usd(4_000),
    raised: usd(225),
    backerCount: 9,
    urgency: 4,
    status: "active",
    endsAt: inDays(12),
  },
  {
    id: "girls-stem-club",
    title: "Girls' STEM Club",
    categoryId: "education",
    facilitator: "STEM Futures Network",
    summary: "Science kits and weekly sessions for girls in secondary school.",
    facets: { cause: "Books & learning", group: "Youth", region: "South Asia" },
    tags: ["secondary school", "girls"],
    goal: usd(3_000),
    raised: usd(400),
    backerCount: 4,
    urgency: 3,
    status: "active",
    endsAt: inDays(26),
  },
  {
    id: "new-reading-corner",
    title: "New Reading Corner",
    categoryId: "education",
    facilitator: "Neighbourhood Library Volunteers",
    summary: "A reading corner for early readers in a new community centre.",
    facets: { cause: "Books & learning", group: "Children", region: "Latin America" },
    tags: ["early years"],
    goal: usd(1_500),
    raised: usd(0),
    backerCount: 0,
    urgency: 2,
    status: "verified",
    endsAt: inDays(30),
  },
  {
    id: "lupus-support",
    title: "Lupus Patient Support Fund",
    categoryId: "health",
    facilitator: "Rare Disease Alliance",
    summary: "Medication and clinic transport for lupus patients.",
    facets: { cause: "Rare diseases", group: "Adults", region: "Europe" },
    tags: ["rare disease"],
    goal: usd(8_000),
    raised: usd(1_200),
    backerCount: 21,
    urgency: 5,
    status: "active",
    endsAt: inDays(8),
  },
  {
    id: "mobile-clinic",
    title: "Mobile Eye Clinic",
    categoryId: "health",
    facilitator: "Clear Sight Outreach",
    summary: "Monthly eye tests and glasses for elderly people in remote villages.",
    facets: { cause: "Primary care", group: "Elderly", region: "Southeast Asia" },
    tags: ["eye care"],
    goal: usd(5_000),
    raised: usd(490),
    backerCount: 14,
    urgency: 3,
    status: "active",
    endsAt: inDays(18),
  },
  {
    id: "shoreline-trees",
    title: "Lake Shoreline Trees",
    categoryId: "environment",
    facilitator: "Lakeside Conservation Group",
    summary: "Planting native trees to stop erosion along a lake shore.",
    facets: { cause: "Conservation", group: "Community", region: "East Africa" },
    tags: ["trees", "lakes"],
    goal: usd(5_000),
    raised: usd(920),
    backerCount: 33,
    urgency: 3,
    status: "active",
    endsAt: inDays(15),
  },
  {
    id: "village-borehole",
    title: "Village Borehole Repair",
    categoryId: "water",
    facilitator: "Village Water Committee",
    summary: "Repair the pump that serves 400 households.",
    facets: { cause: "Clean water", group: "Community", region: "West Africa" },
    tags: ["borehole"],
    goal: usd(3_500),
    raised: usd(430),
    backerCount: 12,
    urgency: 5,
    status: "active",
    endsAt: inDays(5),
  },
];


const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

// Sample evidence. Real entries come from milestone uploads checked by the Milestone Agent.
export const impactUpdates: ImpactUpdate[] = [
  { id: "u1", projectId: "lanet-library", title: "First 120 books shelved", caption: "Receipt matched the tranche within 2%; supplier as planned.", kind: "photo", date: daysAgo(3), tranche: usd(300) },
  { id: "u2", projectId: "shoreline-trees", title: "400 seedlings planted", caption: "Photo dated inside the milestone window; no duplicate images.", kind: "photo", date: daysAgo(6), tranche: usd(450) },
  { id: "u3", projectId: "village-borehole", title: "Pump parts receipt", caption: "Receipt total 3,480 against a 3,500 tranche.", kind: "receipt", date: daysAgo(8), tranche: usd(350) },
  { id: "u4", projectId: "mobile-clinic", title: "62 eye tests in one day", caption: "Clinic log and photos uploaded by the facilitator.", kind: "photo", date: daysAgo(11) },
  { id: "u5", projectId: "kaptembwo-desks", title: "Carpenter's quote approved", caption: "Admin approved a tranche above the auto-release threshold.", kind: "receipt", date: daysAgo(13), tranche: usd(500) },
  { id: "u6", projectId: "lupus-support", title: "Monthly medication delivered", caption: "Pharmacy receipt and delivery photo.", kind: "photo", date: daysAgo(15), tranche: usd(400) },
];

// Sample stories (fictional people) to show the layout until backers opt in to share theirs.
export const backerStories: BackerStory[] = [
  { id: "s1", quote: "I only gave a little, but seeing 16 people back the library made it feel like ours.", name: "Sample backer A", role: "Student, monthly Giving Agent", projectId: "lanet-library" },
  { id: "s2", quote: "The receipt check is why I trust it. I can see exactly what my money bought.", name: "Sample backer B", role: "Nurse, backs health projects", projectId: "mobile-clinic" },
  { id: "s3", quote: "My agent skipped a project I'd excluded and told me why. That's the control I wanted.", name: "Sample backer C", role: "Engineer, set up a mandate", projectId: "village-borehole" },
];

export const sponsors: Sponsor[] = [
  { id: "sp1", name: "Sponsor One", pool: usd(5_000) },
  { id: "sp2", name: "Sponsor Two", pool: usd(3_000) },
  { id: "sp3", name: "Sponsor Three", pool: usd(1_500) },
  { id: "sp4", name: "Sponsor Four", pool: usd(500) },
];
