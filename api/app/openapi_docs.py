"""Descriptions and examples for the OpenAPI spec, in one place.

`document(spec)` fills in whatever the models and routes don't describe themselves: field,
schema, parameter, operation and request-body descriptions, examples everywhere, named enums
and error response bodies. Anything already described in code wins. It then writes the spec as
OpenAPI 3.0.3 (nullable fields, plain minimums), the version SDK generators such as APIMatic
validate against; FastAPI produces 3.1. tests/test_spec.py fails if a field, schema or parameter is
left without a description, so new code has to add one here or in the model.
"""

import copy
from typing import Any

TAGS = [
    {"name": "catalogue", "description": "Categories and projects: listing with filters, detail, funding history, impact stories."},
    {"name": "donations", "description": "Giving through PayPal: create and capture orders, category split preview."},
    {"name": "donors", "description": "Donor profile, report, Giving Agent mandate, monthly subscription and approvals. No login yet: routes take the donor id."},
    {"name": "rounds", "description": "Matching rounds and the leaderboard (projected while open, final after close)."},
    {"name": "admin", "description": "Admin console: verification, Watchdog cases, milestones, payouts, round close, reconciliation, logs. Bearer ADMIN_TOKEN."},
    {"name": "internal (agents)", "description": "For the agent service only: every money action is re-checked here. Bearer INTERNAL_TOKEN."},
    {"name": "agents (public)", "description": "Public, read-only trace of what the agents did: runs, ordered steps and the activity feed. No auth; donor and payer identifiers never leave the API."},
    {"name": "webhooks", "description": "PayPal calls these; authenticated by PayPal's signature, not a token."},
    {"name": "paypal", "description": "Public PayPal settings for the website's JS SDK, and the sandbox test checkout."},
    {"name": "system", "description": "Service health, for uptime checks and waking the free Render instance."},
]
CONTACT = {"name": "Community Giving core API (Person 1)", "url": "https://github.com/The-Panthera-company/Paypal-demo"}
LICENSE = {"name": "MIT", "url": "https://opensource.org/licenses/MIT"}
SECURITY = {
    "HTTPBearer": (
        "Bearer token in the Authorization header. /admin/* takes ADMIN_TOKEN (the admin console, server side); "
        "/internal/* takes INTERNAL_TOKEN (the agent service). Missing or wrong token: 401; token not configured on "
        "the server: 503."
    )
}

# --- schemas ---------------------------------------------------------------------------------

SCHEMAS = {
    "DonorBoardRow": "One donor's numbers for the round, for each ladder (given, matching unlocked, multiplier, reach, agent-given, impact points).",
    "DonorBoardOut": "A round's donor ladders. Names appear only for donors who opted in.",
    "ActiveMandate": "A mandate the Giving Agent should run now, with the donor's remaining funded balance.",
    "AgentStatusOut": "The global agent kill switch: whether agents are paused, why, since when, and who last changed it.",
    "AgentToggleIn": "An admin's reason for pausing or resuming every money-moving agent route.",
    "Allocation": "One project's share of a category gift.",
    "ApprovalIn": "The donor's answer to an agent gift above their approval threshold.",
    "AuditIn": "A decision an agent or person took, for the admin's agent log.",
    "AuditOut": "An entry in the agent log.",
    "AuditVerifyOut": "The result of recomputing the audit hash chain: whether it is intact, how many rows were checked, the first bad row and the current head hash.",
    "CaseIn": "A Watchdog rule hit: freezes the project's matching and opens a case for an admin.",
    "CaseOut": "A Watchdog case and its current state.",
    "CaseResolveIn": "An admin's resolution of a Watchdog case.",
    "CaseStatus": "open: matching frozen, waiting for an admin; cleared: a false alarm; confirmed: the flagged donors count as one person.",
    "CategoryOut": "A category and how many listed projects it has.",
    "CategoryPreviewIn": "A category gift to preview before paying: amount, split rule and exclusions.",
    "CategoryPreviewOut": "Where a category gift would go, and which projects the donor's exclusions removed.",
    "CheckedDonationIn": "A gift the Giving Agent wants to make from a donor's funded balance.",
    "CheckedDonationOut": "The API's answer to a requested agent gift, after re-checking the mandate.",
    "CreateOrderIn": "What the donor is giving to and how much. The browser never decides what gets recorded: capture checks PayPal's answer against this.",
    "CreateOrderOut": "The PayPal order for the JS SDK's createOrder, and the donation it belongs to.",
    "DocumentIn": "A project document: registration, plan, receipt or photo. Receipts and photos with a milestone_id are that milestone's evidence.",
    "DocumentKind": "registration and plan support verification; receipt and photo are milestone evidence.",
    "DocumentOut": "A stored project document with the fields extracted from it.",
    "DonationOut": "A donation and its PayPal references.",
    "DonationEventOut": "One donation event for the Watchdog: captured or refunded, with internal Donor ids (never PayPal payer ids).",
    "DonationStatus": "created: order made, not paid; pending: PayPal is holding the payment; captured: received; failed: declined, denied or abandoned; refunded: refunded in full.",
    "DonorOut": "A donor's profile. Donations are anonymous unless show_on_leaderboard is true.",
    "DonorReport": "\"Where your money went\": gifts, matching unlocked, impact updates and the Giving Agent's report.",
    "DonorUpdate": "Profile fields a donor can change; send only the ones to change.",
    "ErrorOut": "Every error: detail.error is a stable code to branch on, detail.message is for people.",
    "ExcludedProject": "A project the donor's exclusions removed from a category gift, and the tag that matched.",
    "FundingPoint": "Cumulative amount raised and backers at the end of one day.",
    "HTTPValidationError": "The request didn't match the expected shape (wrong type, missing field). Each item says where and why.",
    "LeaderboardOut": "A round's leaderboard: projected while the round is open, final once it has closed.",
    "LeaderboardRow": "One project's place and matching in the round.",
    "MandateIn": "The rules the Giving Agent must follow for a donor. The core API enforces them on every gift.",
    "MandateOut": "A donor's Giving Agent mandate and their funded balance.",
    "MandateRunIn": "A Giving Agent run, recorded before it asks for gifts.",
    "MandateRunOut": "A recorded Giving Agent run: candidates, scores, choices and the report.",
    "MilestoneChecks": "The Milestone Agent's four rule checks on a tranche's evidence.",
    "MilestoneOut": "A project milestone: a tranche of money released with evidence.",
    "MilestoneReviewIn": "An admin's decision on a held tranche.",
    "MilestoneStatus": "open: waiting for evidence; evidence_submitted: evidence uploaded; held: sent to an admin; released: paid out.",
    "PayoutAccountIn": "Where a project's tranches are paid.",
    "PayoutAccountOut": "A project's payout account.",
    "PayoutItem": "One payment in a PayPal Payouts batch.",
    "PayoutOut": "A PayPal Payouts batch with a deterministic sender_batch_id (PayPal refuses a reused one for 30 days).",
    "PayoutRequestIn": "The Milestone Agent's request to release a tranche, with its checks and summary.",
    "PayoutRequestOut": "Whether the tranche was released (and paid) or held for an admin.",
    "PayoutStatus": "pending: not sent yet; processing: PayPal is paying; success: PayPal processed the batch; denied: PayPal refused it.",
    "PendingApproval": "An agent gift above the donor's approval threshold, waiting for their yes.",
    "ProjectApplicationIn": "A new project's application, reviewed by an admin before it is listed.",
    "ProjectDetail": "A project with its summary and milestones.",
    "ProjectStatus": "draft and pending_review aren't public; verified and active are listed; frozen is delisted; completed is finished.",
    "ProjectSummary": "A project as listed: totals, tags, facets and projected match.",
    "ReconciliationIssue": "One check that found something wrong or worth attention.",
    "ReconciliationOut": "Money in and out, and every check that the records add up.",
    "ReportGift": "One of the donor's gifts and the matching it unlocked.",
    "RoundOut": "A matching round and its rules.",
    "RoundStatus": "scheduled; open: taking donations; closing: ended, waiting for open Watchdog cases; closed: final results written.",
    "StoryOut": "An impact update: a released milestone with its evidence.",
    "SubscriptionIn": "A monthly amount for the Giving Agent's budget.",
    "SubscriptionOut": "A donor's monthly PayPal subscription for the Giving Agent's budget.",
    "SweepOut": "What the stuck-order sweep did with each open PayPal order.",
    "TargetType": "PROJECT: one project; CATEGORY: split across a category's projects; AGENT: a Giving Agent gift (with project) or budget top-up (without).",
    "ValidationError": "One problem with the request: where it is and what is wrong.",
    "VerifyIn": "An admin's verification decision on a project under review.",
    "WebhookAck": "What the API did with a PayPal webhook delivery.",
    "WebhookEventOut": "A PayPal webhook delivery the API accepted, and the result.",
    "EvidenceMilestone": "A tranche with evidence waiting for the Milestone Agent, and its documents.",
    "MatchPreviewItem": "What one gift would add to one project's match.",
    "MatchPreviewOut": "Estimated matching a gift would add, per project, on the round's live inputs.",
    "MilestonePlanIn": "One tranche in a project's application: what it pays for, how much, and when.",
    "OwnerTokenOut": "A project's new owner token for document uploads.",
    "ProjectApplicationOut": "The new project (pending review) and its owner token.",
    "RefundIn": "An admin's refund: how much (default: all that's left) and why.",
    "RefundOut": "What PayPal did with the refund and where the donation stands.",
    "RoundIn": "A new matching round: its window, pool and matching rules.",
    "RoundResultRow": "One project's outcome in a round: projected and final match.",
    "RoundResultsOut": "A round's outcome: totals and each project's projected and final match.",
    "RoundUpdateIn": "Changes to a scheduled or open round; fields left out stay as they are.",
    "SponsorOut": "One contribution to a round's matching pool.",
    "SponsorsOut": "Who added to a round's matching pool, largest first.",
    "TraceStep": "One step an agent took: the tool it called, the rule result and a short reason. No prompts and no donor identifiers.",
    "AgentRunChoice": "A project the agent chose and the amount it asked the rules engine for.",
    "AgentRunSkip": "A project the agent left out, with the reason.",
    "AgentRunOut": "A public Giving Agent run: ordered trace, chosen projects, skipped projects and the report. No donor identifiers.",
    "AgentActivityOut": "One recent agent or admin action for the public activity feed.",
}

# --- fields: by name, with per-schema wording where a name means different things ------------

FIELDS = {
    "impact_points": "(given + matching unlocked) in dollars, times a reach bonus of 1 + 0.25 per extra project.",
    "agent_given_cents": "What the donor's Giving Agent gave for them in the round, in cents.",
    "categories_reached": "Distinct categories the donor's money reached.",
    "projects_backed": "Distinct projects the donor's money reached, including through category gifts.",
    "multiplier": "Matching unlocked per dollar given.",
    "given_cents": "Everything the donor gave in the round, in cents (agent budget top-ups excluded).",
    "is_me": "True on the row of the donor passed as `me`.",
    "alias": "Stable anonymous name that does not reveal the donor id, e.g. Donor 3FA2C1.",
    "action": "What was done, e.g. checked_donation, case_opened, payout_request.",
    "active": "Whether the Giving Agent runs for this mandate; false pauses it.",
    "actor": "Who acted: giving-agent, milestone-agent, watchdog-agent, admin, donor, system or paypal.",
    "agent_report": "The Giving Agent's latest run report for this donor, if any.",
    "allocations": "Each project's share, largest first; the shares add up to amount_cents.",
    "amount_cents": "Amount in cents (minor units of currency).",
    "approve": "true to approve, false to decline.",
    "approve_url": "Send the donor here to approve in PayPal (only while APPROVAL_PENDING).",
    "backer_count": "Number of different people who gave (one PayPal account = one person).",
    "beneficiary_group": "Who the project helps, e.g. children, adults, elderly, community.",
    "body": "What happened, in a sentence: the amount released and what it included.",
    "capped": "Whether the project hit a cap (its share of the category pool or its remaining goal).",
    "category": "The category's name.",
    "category_id": "Category id.",
    "cause": "What the project does, as a facet, e.g. literacy, clean water.",
    "check": "Which check found it, e.g. stuck_orders, captured_without_ledger.",
    "checked": "How many open orders were looked up at PayPal.",
    "checks": "The four rule checks on the evidence.",
    "computed_at": "When these numbers were computed.",
    "created_at": "When it was created (UTC).",
    "crowd_cents": "The share that follows the crowd score (80% of the category pool by default).",
    "currency": "ISO 4217 currency code. All PayPal money moves in USD.",
    "date": "The day (UTC).",
    "dated_in_window": "The evidence is dated inside the milestone's window.",
    "captured_at": "When PayPal captured the donation (UTC).",
    "decisions": "The run's reasoning: candidates with scores, chosen projects with amounts, skipped projects with reasons.",
    "display_name": "Name shown on the leaderboard if the donor opts in.",
    "donation_id": "Donation id.",
    "donor_created_at": "When the donor record was created (UTC).",
    "donor_id": "Donor id.",
    "due_date": "When the milestone should be reached.",
    "ends_at": "When the round ends (UTC); donations after this go to the next round.",
    "errors": "Orders that couldn't be settled, with the reason.",
    "event_id": "PayPal's webhook event id (WH-...).",
    "event_type": "PayPal's event type, e.g. PAYMENT.CAPTURE.COMPLETED.",
    "evidence": "What triggered the rule. donor_ids: the suspected donors, counted as one person if the case is confirmed.",
    "evidence_urls": "Links to the milestone's receipts and photos.",
    "excluded": "Projects removed by the donor's excluded tags.",
    "excluded_tags": "Tags the donor won't give to; matching projects are left out (case-insensitive).",
    "extracted_fields": "Fields the Verification step read from the document, e.g. total, supplier, date.",
    "file_url": "Where the document is stored.",
    "flags": "Problems the Verification step found in the document.",
    "floor_cents": "The equal share every eligible project gets (20% of the category pool by default).",
    "floor_pct": "Percent of each category pool shared equally among its projects.",
    "frozen_at": "When the project's matching was frozen.",
    "generated_at": "When the report was made (UTC).",
    "gifts": "The donor's gifts, newest first. Agent budget top-ups are left out.",
    "goal_cents": "Funding goal in cents.",
    "hide_location": "Hide the project's region on public pages.",
    "id": "Id.",
    "inputs": "The data the decision was based on.",
    "interests": "What the donor cares about (categories, causes), set at sign-up.",
    "is_guest": "Paid by card without a PayPal account; counts at half weight in matching.",
    "issues": "Problems found; empty when everything adds up.",
    "items": "The payments in this batch.",
    "kind": "Document type: registration, plan, receipt or photo.",
    "loc": "Where the problem is: body, query or path, then the field.",
    "mandate_id": "Mandate id.",
    "mandate_run_id": "The Giving Agent run that chose this gift (from POST /internal/mandate-runs).",
    "match_amount_cents": "Matching money added to this milestone at round close, paid out with it.",
    "match_cents": "Matching money for the project: projected while the round is open, final once closed.",
    "match_unlocked_cents": "This donor's share of the matching their gifts unlocked (square-root share of each project's match).",
    "matched_tag": "The excluded tag that removed the project.",
    "matching_frozen": "A Watchdog case froze this project's matching (donations still work).",
    "matching_pool_cents": "The round's matching pool in cents.",
    "milestone_id": "Milestone id.",
    "milestones": "The project's milestones in order.",
    "monthly_amount_cents": "Charged every month and credited to the Giving Agent's funded balance.",
    "monthly_budget_cents": "Most the agent may give in a calendar month.",
    "msg": "What is wrong.",
    "name": "Name.",
    "note": "Optional note, kept in the audit log.",
    "order_id": "PayPal order id: return it from the JS SDK's createOrder.",
    "owner_donor_id": "Internal Donor.id of the project's owner, or null when it has none.",
    "payout_id": "The payout batch sending this tranche, if one was created.",
    "payout_item_id": "PayPal's id for this payment, once sent.",
    "paypal_batch_id": "PayPal's id for the batch, once it accepted it.",
    "paypal_capture_id": "PayPal's capture id (refunds refer to it). For subscription charges, the sale id.",
    "paypal_order_id": "PayPal's order id. Null for agent gifts, which are moves from a funded balance.",
    "per_person_cap_cents": "Only this much of one person's giving to one project counts for matching.",
    "per_project_max_cents": "Most the agent may give one project in a calendar month.",
    "photo_not_duplicate": "The photo isn't a copy of an earlier upload (image hash).",
    "project_cap_pct": "No project gets more than this percent of its category pool.",
    "project_count": "Listed (verified or active) projects in the category.",
    "project_id": "Project id.",
    "project_title": "The project's title.",
    "projected_match_cents": "Projected matching from the open round, refreshed every 5 minutes.",
    "raised_cents": "Raised so far in cents: captured gifts plus category shares, minus refunds.",
    "rank": "Position by match, 1 = most.",
    "reason": "Why, in plain words.",
    "receipt_total_within_10pct": "The receipts add up to the tranche amount within 10%.",
    "received_at": "When the API received it (UTC).",
    "region": "Where the project is. Null when the project hides its location.",
    "report_text": "The run's report for the donor, written from the scores.",
    "resolved_by": "Who resolved the case.",
    "resource_id": "The PayPal resource the event is about (capture, refund, payout item...).",
    "result": "processed, duplicate, ignored, unmatched or mismatch.",
    "round_id": "Round id.",
    "rows": "Projects ranked by match.",
    "rule": "Which rule.",
    "rule_result": "ok, or the rule that blocked it, e.g. over_per_project_max.",
    "run_at": "When the run happened (UTC).",
    "score": "Crowd score: (sum of square roots of each person's gift)^2 minus the sum of gifts, in cents.",
    "sender_batch_id": "Our deterministic batch id, e.g. milestone-7-USD; a retry gets -retry1, -retry2.",
    "seq": "Order of the milestone in the project (1 = first).",
    "severity": "error: the records don't add up; warning: needs attention.",
    "show_on_leaderboard": "Show the donor's display name on the public leaderboard (off by default).",
    "starts_at": "When the round starts (UTC).",
    "status": "Current status.",
    "subscription_id": "PayPal's subscription id (I-...): return it from the JS SDK's createSubscription.",
    "summary": "A short description of the project.",
    "supplier_matches_plan": "The supplier on the receipts is the one in the project's plan.",
    "tags": "Neutral tags describing the project; donors can exclude any of them.",
    "target_type": "What the donation is for: PROJECT, CATEGORY or AGENT.",
    "title": "Title.",
    "total_given_cents": "Captured gifts in cents; refunded gifts are listed but not counted.",
    "totals": "Money in and out, in cents.",
    "type": "Error type.",
    "unchanged": "Orders still open at PayPal.",
    "updates": "Impact stories from projects the donor backed, newest first.",
    "urgency": "1 (low) to 5 (urgent), set at verification.",
    "verified_at": "When an admin verified the project.",
    "via": "How it was given: PROJECT, CATEGORY or AGENT.",
    "first_bad_id": "Id of the first row that failed verification; null when the chain is intact.",
    "first_bad_reason": "Why that row failed: missing hash, sequence mismatch, previous-hash mismatch or content hash mismatch.",
    "hash": "SHA-256 of this row's canonical payload; the next row stores it as prev_hash.",
    "head_hash": "Hash of the last row checked, or an empty string when the log is empty.",
    "paused": "True while the global agent kill switch is on.",
    "prev_hash": "The previous row's hash, or an empty string for the first row.",
    "since": "When the switch was last changed (UTC).",
    "updated_by": "Who last moved the switch, e.g. admin.",
    "valid": "True only when every row matches its sequence, previous hash and content hash.",
}

SCHEMA_FIELDS = {
    ("ErrorOut", "detail"): "error: a stable code such as PROJECT_NOT_OPEN; message: for people; sometimes more keys (restart: true on a declined card).",
    ("HTTPValidationError", "detail"): "One item per problem.",
    ("ReconciliationIssue", "detail"): "What the check looks for.",
    ("ReconciliationIssue", "refs"): "Ids of the rows involved (donations, payouts, milestones...).",
    ("CaseIn", "rule"): "new_payer_burst, reciprocal_backing, owner_donation, refund_spike or collusion_cluster.",
    ("CaseOut", "rule"): "The Watchdog rule that fired.",
    ("DonationEventOut", "donor_id"): "Internal Donor.id integer, never a PayPal payer id.",
    ("DonationEventOut", "owner_donor_id"): "Internal Donor.id of the project owner, never a PayPal payer id.",
    ("CreateOrderIn", "rule"): "CATEGORY only: crowd (20% equally, 80% by backers; default), equal, or closest_to_goal.",
    ("CategoryPreviewOut", "rule"): "The split rule used.",
    ("CategoryPreviewIn", "amount_cents"): "The gift to preview, in cents.",
    ("CreateOrderIn", "amount_cents"): "The gift in cents, within the limits from GET /config/paypal.",
    ("CreateOrderIn", "project_id"): "PROJECT donations only.",
    ("CreateOrderIn", "category_id"): "CATEGORY donations only.",
    ("CreateOrderIn", "excluded_tags"): "CATEGORY only: tags the donor won't give to.",
    ("CheckedDonationIn", "amount_cents"): "The gift in cents, from the donor's funded balance.",
    ("CheckedDonationIn", "reason"): "Why the agent chose this project; kept in the audit log.",
    ("CheckedDonationOut", "status"): "recorded, awaiting_donor_approval or rejected.",
    ("CheckedDonationOut", "reason"): "What the checks found.",
    ("CheckedDonationOut", "donation_id"): "The donation, unless it was rejected.",
    ("PendingApproval", "reason"): "Why it is waiting, e.g. above the donor's approval threshold.",
    ("PayoutRequestOut", "status"): "released (and sent to PayPal Payouts) or held_for_admin.",
    ("PayoutRequestOut", "reason"): "Why it was held, or that every check passed.",
    ("AuditIn", "reason"): "Why, in plain words.",
    ("AuditOut", "reason"): "Why, in plain words.",
    ("AuditOut", "seq"): "Position in the audit hash chain (1 = first).",
    ("AuditVerifyOut", "checked"): "How many audit rows were recomputed before the check finished.",
    ("AgentStatusOut", "reason"): "Why agents are paused, or why they were last resumed.",
    ("AgentToggleIn", "reason"): "Why the admin paused or resumed agents; kept in the audit log.",
    ("DonationOut", "status"): "created, pending, captured, failed or refunded.",
    ("ReportGift", "status"): "pending, captured or refunded.",
    ("MilestoneOut", "status"): "open, evidence_submitted, held or released.",
    ("CaseOut", "status"): "open, cleared or confirmed.",
    ("PayoutOut", "status"): "pending, processing, success or denied.",
    ("ProjectSummary", "status"): "verified or active (listed), or frozen, completed, draft, pending_review.",
    ("ProjectDetail", "status"): "verified or active (listed), or frozen, completed, draft, pending_review.",
    ("RoundOut", "status"): "scheduled, open, closing or closed.",
    ("SubscriptionOut", "status"): "APPROVAL_PENDING, ACTIVE, SUSPENDED, CANCELLED or EXPIRED.",
    ("PayoutItem", "status"): "NEW before sending, then PayPal's: PENDING, SUCCESS, UNCLAIMED, FAILED, RETURNED, BLOCKED; RETRIED once retried.",
    ("PayoutItem", "receiver"): "The project's PayPal email; null until it has a payout account.",
    ("PayoutItem", "error"): "Why it wasn't sent, e.g. NO_PAYOUT_ACCOUNT or a PayPal issue.",
    ("PayoutItem", "amount_cents"): "The tranche plus its match, in cents.",
    ("MilestoneOut", "amount_cents"): "The tranche in cents.",
    ("Allocation", "amount_cents"): "This project's share in cents.",
    ("ReportGift", "amount_cents"): "The gift in cents.",
    ("PendingApproval", "amount_cents"): "The gift in cents.",
    ("CategoryPreviewOut", "amount_cents"): "The gift previewed, in cents.",
    ("DonationOut", "amount_cents"): "The donation in cents.",
    ("ReportGift", "project_title"): "The project, or how a category gift was split.",
    ("ReportGift", "project_id"): "Null for a category gift (see project_title).",
    ("CategoryOut", "name"): "The category's name, e.g. Education.",
    ("RoundOut", "name"): "The round's name, e.g. November round.",
    ("StoryOut", "title"): "The milestone's title.",
    ("MilestoneOut", "title"): "What the tranche pays for.",
    ("StoryOut", "created_at"): "When the tranche was released (UTC).",
    ("WebhookAck", "status"): "processed, duplicate (already handled), ignored, unmatched (not ours) or mismatch (amount or id disagreed).",
    ("SweepOut", "captured"): "Donation ids captured or recorded now.",
    ("SweepOut", "failed"): "Donation ids voided, declined or abandoned (never approved).",
    ("StoryOut", "id"): "Story id (the milestone's id).",
    ("CreateOrderIn", "sponsor_name"): "POOL only: the name on the round's sponsor list; leave out to be anonymous.",
    ("EvidenceMilestone", "documents"): "Everything uploaded for this tranche, oldest first.",
    ("ProjectApplicationOut", "milestone_ids"): "The tranches created from the plan, in order.",
    ("RefundOut", "refund_id"): "PayPal's refund id.",
    ("RefundOut", "refunded_total_cents"): "Everything refunded on this donation so far (booked refunds only).",
    ("RoundResultsOut", "is_final"): "True once the round has closed and the match is fixed.",
    ("RoundResultsOut", "matched_cents"): "Match shared out: final once closed, projected before.",
    ("SponsorOut", "given_at"): "When the contribution was captured (UTC).",
    ("SponsorsOut", "total_cents"): "Everything sponsors added to the pool.",
}
for _schema in ("ActiveMandate", "AuditOut", "CaseOut", "CategoryOut", "DocumentOut", "DonationOut", "DonorOut",
                "MandateOut", "MandateRunOut", "MilestoneOut", "PayoutOut", "ProjectDetail", "ProjectSummary", "RoundOut"):
    SCHEMA_FIELDS.setdefault((_schema, "id"), f"{_schema.removesuffix('Out').removesuffix('Detail').removesuffix('Summary')} id.")
SCHEMA_FIELDS[("ProjectDetail", "id")] = SCHEMA_FIELDS[("ProjectSummary", "id")] = "Project id."
SCHEMA_FIELDS[("ActiveMandate", "id")] = "Mandate id."
SCHEMA_FIELDS[("AuditOut", "id")] = "Log entry id."
SCHEMA_FIELDS[("CaseOut", "id")] = "Case id."
SCHEMA_FIELDS[("MandateRunOut", "id")] = "Run id."
SCHEMA_FIELDS[("PayoutOut", "id")] = "Payout batch id."

PARAMS = {
    "me": "Donor id of the caller, to mark their own row (demo: no login yet).",
    "case_id": "Watchdog case id.",
    "category_id": "Only projects in this category.",
    "cause": "Only projects with this cause, e.g. literacy.",
    "beneficiary_group": "Only projects helping this group, e.g. children.",
    "region": "Only projects in this region (projects that hide their location never match).",
    "exclude_tags": "Comma-separated tags; projects carrying any of them are left out.",
    "q": "Search in project titles.",
    "sort": "urgency (most urgent first), newest, or fewest_backers.",
    "limit": "Most items to return.",
    "offset": "Items to skip, for paging.",
    "donation_id": "Donation id.",
    "donor_id": "Donor id (no login yet; demo logins map to donor ids).",
    "milestone_id": "Milestone id.",
    "order_id": "PayPal order id from create order.",
    "payout_id": "Payout batch id.",
    "project_id": "Project id.",
    "round_id": "Round id.",
    "status": "Only items in this status.",
    "actor": "Only entries by this actor, e.g. giving-agent.",
    "early": "Close before the round's end time.",
    "run_id": "Giving Agent run id.",
    "before_id": "Return entries older than this audit-log id (cursor paging).",
    "include_hash": "Include each audit row's seq, prev_hash and hash for independent checks.",
    "since": "Only donations captured at or after this ISO timestamp (UTC).",
}

# --- examples for schemas that have none ------------------------------------------------------

# Hand-written where a generated example would be invalid or misleading.
EXAMPLES = {
    "CreateOrderIn": {"target_type": "PROJECT", "project_id": 1, "amount_cents": 2000},
    "CaseIn": {
        "project_id": 6,
        "rule": "collusion_cluster",
        "evidence": {
            "donor_ids": [12, 13, 14],
            "graph": {
                "nodes": [
                    {"id": 12, "type": "donor", "label": "Donor 3FA2C1"},
                    {"id": 13, "type": "donor", "label": "Donor 81B4D0"},
                    {"id": 14, "type": "donor", "label": "Donor C27A9E"},
                    {"id": 6, "type": "project", "label": "Lanet Library"},
                ],
                "edges": [
                    {"source": 12, "target": 6, "weight": 1},
                    {"source": 13, "target": 6, "weight": 1},
                    {"source": 14, "target": 6, "weight": 1},
                ],
            },
        },
    },
    "CaseResolveIn": {"action": "confirm", "remove_project": False, "note": "Three accounts shared a device"},
    "AuditIn": {"actor": "giving-agent", "action": "skip", "inputs": {"project_id": 5}, "rule_result": "excluded_tag",
                "reason": "Tagged gambling-recovery, which the donor excluded"},
    "MandateIn": {"monthly_budget_cents": 1000, "categories": [2], "excluded_tags": ["faith-based"],
                  "per_project_max_cents": 400, "approval_threshold_cents": 500,
                  "weight_overrides": {"few_backers": 45}, "active": True},
    "ProjectApplicationIn": {"title": "Lanet Library", "facilitator": "Lanet Community Library Group", "summary": "A lending library for three primary schools in Lanet.",
                             "category_id": 2, "tags": ["books", "literacy"], "cause": "literacy",
                             "beneficiary_group": "children", "region": "Nakuru", "hide_location": False,
                             "goal_cents": 600000, "urgency": 4,
                             "milestones": [
                                 {"title": "Shelves for three schools", "amount_cents": 200000, "due_date": "2026-12-15"},
                                 {"title": "400 books", "amount_cents": 250000, "due_date": "2027-01-31"},
                                 {"title": "Librarian, first term", "amount_cents": 150000, "due_date": "2027-03-31"},
                             ],
                             "payout_email": "lanet.library@example.com"},
}

SAMPLES = {
    "id": 1, "project_id": 1, "category_id": 2, "donor_id": 1, "donation_id": 4, "milestone_id": 7, "mandate_id": 1,
    "mandate_run_id": 5, "round_id": 1, "payout_id": 1, "case_id": 2, "currency": "USD", "title": "Lanet Library",
    "project_title": "Lanet Library", "name": "Education", "reason": "Few backers (4), 60% funded, receipts uploaded",
    "note": "Checked by phone", "approve": True, "kind": "receipt", "file_url": "https://files.example.com/receipt-7.jpg",
    "rule": "crowd", "excluded_tags": ["faith-based"], "tags": ["books", "literacy"], "matched_tag": "faith-based",
    "display_name": "Wanjiru", "show_on_leaderboard": True, "interests": {"categories": [2]},
    "cause": "literacy", "beneficiary_group": "children", "region": "Nakuru", "urgency": 4, "goal_cents": 600000,
    "hide_location": False, "monthly_amount_cents": 2500, "date": "2026-11-03", "raised_cents": 12000, "backer_count": 5,
    "decisions": {"chosen": [{"project_id": 2, "amount_cents": 300}]},
    "report_text": "USD 3.00 to Kaptembwo Desks: 4 backers, 60% funded.", "paypal_email": "lanet-library@example.com",
    "loc": ["body", "amount_cents"], "msg": "Field required", "type": "missing",
}


def _example_value(name: str, prop: dict, schemas: dict, depth: int = 0) -> Any:
    if name in SAMPLES:
        return SAMPLES[name]
    if "$ref" in prop:
        target = schemas.get(prop["$ref"].split("/")[-1], {})
        return target.get("example") or (target.get("enum") or [None])[0] or (_object_example(target, schemas, depth + 1) if depth < 2 else {})
    if "anyOf" in prop:
        first = next((p for p in prop["anyOf"] if p.get("type") != "null"), {})
        return _example_value(name, first, schemas, depth)
    if "enum" in prop:
        return prop["enum"][0]
    t = prop.get("type")
    if name.endswith("_cents"):
        return 2500
    if t == "boolean":
        return True
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "array":
        return [_example_value(name.rstrip("s"), prop.get("items", {}), schemas, depth)]
    if t == "object":
        return {}
    if prop.get("format") == "date-time":
        return "2026-11-03T09:00:00Z"
    if prop.get("format") == "date":
        return "2026-12-15"
    return "Receipts match the plan" if name == "summary" else name.replace("_", " ")


def _object_example(schema: dict, schemas: dict, depth: int = 0) -> dict:
    return {name: _example_value(name, prop, schemas, depth) for name, prop in schema.get("properties", {}).items()}


# --- operations, parameters and enums ---------------------------------------------------------

OPERATIONS = {
    "donor_leaderboard": "Donor ladders for the round: biggest givers, most matching unlocked, best multiplier, widest reach, Giving Agent gifts and impact points. Anonymous unless the donor opted in.",
    "list_categories": "All categories with how many listed (verified or active) projects each has.",
    "list_projects": "Listed projects with totals, facets and projected match. Filter by category, cause, beneficiary group, region or search text, leave out excluded tags, and sort.",
    "get_project": "One listed or completed project with its summary, totals and milestones. 404 for projects under review or delisted.",
    "create_order": "Create the PayPal order for a donation (project, category, or Giving Agent top-up). Return order_id from the JS SDK's createOrder.",
    "capture_order": "Capture an approved PayPal order and record the donation and ledger entries. Safe to call twice. A declined card answers 422 with restart: true.",
    "get_donation": "One donation and its PayPal references.",
    "get_donor": "A donor's profile.",
    "get_mandate": "The donor's Giving Agent mandate and funded balance. 404 NO_MANDATE until the donor sets one.",
    "get_subscription": "The donor's monthly Giving Agent subscription, if one is pending, active or suspended.",
    "current_round": "The round taking donations now (open, or closing while it waits for Watchdog cases). 404 when none is.",
    "verify_audit_log": "Recompute the audit SHA-256 chain in id order. Reports the first edited, missing or reordered row and stops there.",
    "agent_status": "Whether the global agent kill switch is on, with the reason, time and actor.",
    "pause_agents": "Stop every money-moving agent route with one request. Audit remains writable so agents can record the pause.",
    "resume_agents": "Turn the global agent kill switch back off.",
    "internal_status": "The agent service's read-only view of the kill switch; reachable while paused.",
    "donation_events": "Watchdog's event feed: captured and refunded donations since a timestamp, newest first, with internal Donor ids.",
    "review_queue": "Projects in a status for the admin, by default those waiting for verification.",
    "list_cases": "Watchdog cases, by default the open ones, newest first.",
    "list_payouts": "PayPal Payouts batches, newest first, with each item's status.",
    "get_payout_account": "The PayPal email a project's tranches are paid to.",
    "paypal_config": "Public PayPal settings for the website: client id, currency, environment and donation limits.",
    "health": "Returns ok when the API is up. Use it to wake the free Render instance before a demo.",
    "list_agent_runs": "Newest Giving Agent runs across all mandates, with the same safe projection. Public: no auth and no donor identifiers.",
    "get_agent_run": "One Giving Agent run with its ordered trace, chosen projects and skipped projects. 404 when the run is unknown. Public: no auth and no donor identifiers.",
    "agent_activity": "Recent agent and admin actions for the public activity feed, newest first. Pass before_id to page. No raw inputs and no donor identifiers.",
}

PARAM_EXAMPLES = {
    "category_id": 2, "cause": "literacy", "beneficiary_group": "children", "region": "Nakuru",
    "exclude_tags": "faith-based,stem", "q": "library", "sort": "urgency", "limit": 50, "offset": 0,
    "project_id": 1, "donation_id": 4, "donor_id": 1, "order_id": "8E825560D88497210", "payout_id": 1,
    "round_id": 1, "milestone_id": 7, "case_id": 2, "actor": "giving-agent", "early": True,
    "run_id": 7, "before_id": 100,
    "include_hash": True, "since": "2026-11-08T00:00:00Z",
}

# Literal fields become named enums (APIMatic flags inline enums); same values share one name.
ENUM_NAMES = {
    ("new_payer_burst", "reciprocal_backing", "owner_donation", "refund_spike", "collusion_cluster"): "WatchdogRule",
    ("clear", "confirm"): "CaseAction",
    ("crowd", "equal", "closest_to_goal"): "SplitRuleName",
    ("recorded", "awaiting_donor_approval", "rejected"): "CheckedDonationStatus",
    ("released", "held_for_admin"): "PayoutRequestStatus",
    ("error", "warning"): "IssueSeverity",
    ("processed", "duplicate", "ignored", "unmatched", "mismatch"): "WebhookResult",
    ("urgency", "newest", "fewest_backers"): "ProjectSort",
}


def _hoist_enums(spec: dict) -> None:
    schemas = spec["components"]["schemas"]

    def name_for(values: tuple, hint: str, text: str | None) -> str:
        name = ENUM_NAMES.get(values) or hint
        if name not in schemas:
            schemas[name] = {"type": "string", "enum": list(values), "title": name,
                             "description": text or f"One of: {', '.join(map(str, values))}.",
                             "example": values[0]}
        return name

    def visit(node: dict, hint: str) -> None:
        for key, prop in list(node.get("properties", {}).items()):
            pascal = hint + "".join(w.capitalize() for w in key.split("_"))
            options = prop.get("anyOf", [prop])
            for i, option in enumerate(options):
                if "enum" in option and option.get("type") == "string":
                    ref = {"$ref": f"#/components/schemas/{name_for(tuple(option['enum']), pascal, prop.get('description'))}"}
                    if "anyOf" in prop:
                        prop["anyOf"][i] = ref
                    else:
                        node["properties"][key] = {**ref, **{k: v for k, v in prop.items() if k in ("description",)}}

    for name, schema in list(schemas.items()):
        visit(schema, name)
    for item in spec["paths"].values():
        for op in item.values():
            for param in op.get("parameters", []):
                schema = param.get("schema", {})
                if "enum" in schema and schema.get("type") == "string":
                    pascal = "".join(w.capitalize() for w in param["name"].split("_"))
                    param["schema"] = {"$ref": f"#/components/schemas/{name_for(tuple(schema['enum']), pascal, param.get('description'))}",
                                       **({"default": schema["default"]} if "default" in schema else {})}


# --- OpenAPI 3.0.3 ---------------------------------------------------------------------------


def _to_30(node: Any) -> Any:
    """Rewrite FastAPI's 3.1 schema keywords the 3.0 way, recursively."""
    if isinstance(node, list):
        return [_to_30(n) for n in node]
    if not isinstance(node, dict):
        return node
    node = {k: (v if k in ("example", "examples", "default", "enum") else _to_30(v)) for k, v in node.items()}
    if "anyOf" in node:
        options = [o for o in node["anyOf"] if o.get("type") != "null"]
        if len(options) < len(node["anyOf"]) and len(options) == 1:  # X | None
            extra = {k: v for k, v in node.items() if k != "anyOf"}
            only = options[0]
            node = ({"allOf": [only]} if "$ref" in only else dict(only)) | extra | {"nullable": True}
    if isinstance(node.get("exclusiveMinimum"), (int, float)) and not isinstance(node["exclusiveMinimum"], bool):
        limit = node.pop("exclusiveMinimum")
        if node.get("type") == "integer":
            node["minimum"] = limit + 1
        else:
            node["minimum"], node["exclusiveMinimum"] = limit, True
    if isinstance(node.get("exclusiveMaximum"), (int, float)) and not isinstance(node["exclusiveMaximum"], bool):
        limit = node.pop("exclusiveMaximum")
        if node.get("type") == "integer":
            node["maximum"] = limit - 1
        else:
            node["maximum"], node["exclusiveMaximum"] = limit, True
    if "const" in node:
        node["enum"] = [node.pop("const")]
    if isinstance(node.get("examples"), list) and "in" not in node:  # schema examples, not parameter examples
        values = node.pop("examples")
        node.setdefault("example", values[0] if values else None)
    if "$ref" in node and len(node) > 1:  # 3.0 ignores $ref siblings; the target has its own description
        node.pop("description", None)
        if len(node) > 1:  # e.g. a default next to $ref
            ref = node.pop("$ref")
            node = {"allOf": [{"$ref": ref}], **node}
    if node.get("type") == "array" and node.get("items", {}).get("anyOf") == [{"type": "string"}, {"type": "integer"}]:
        node["items"] = {"type": "string"}  # ValidationError.loc: field names (list indexes come back as numbers)
    return node


# --- examples and sub-schema descriptions ------------------------------------------------------


def _resolve(node: dict, schemas: dict) -> dict:
    while "$ref" in node:
        node = schemas.get(node["$ref"].split("/")[-1], {})
    if "allOf" in node and len(node["allOf"]) == 1:
        return _resolve(node["allOf"][0], schemas) | {k: v for k, v in node.items() if k != "allOf"}
    return node


def _fill(node: dict, name: str, hint: Any, text: str | None, schemas: dict) -> Any:
    """Give an inline schema an example and a description, then do the same for its parts.
    Returns the example used. $ref nodes keep no siblings; their target has its own."""
    if not isinstance(node, dict):
        return hint
    if "$ref" in node:
        target = _resolve(node, schemas)
        return hint if hint is not None else target.get("example", _example_value(name, node, schemas))
    if text and not node.get("description"):
        node["description"] = text
    if "allOf" in node:
        value = _fill(node["allOf"][0], name, hint, None, schemas)
        if value is not None and "example" not in node:
            node["example"] = value
        return value
    value = hint if hint is not None else node.get("example", node.get("default"))
    if value is None:
        value = _example_value(name, node, schemas)
    if node.get("type") == "object" and "properties" in node:
        given = isinstance(value, dict) and bool(value)  # hand-written examples leave fields out on purpose
        value = value if given else {}
        for key, prop in node["properties"].items():
            got = _fill(prop, key, value.get(key), None, schemas)
            if not given:
                value.setdefault(key, got)
            elif key in node.get("required", []):  # e.g. resolved_by on an open case
                value.setdefault(key, None if prop.get("nullable") else got)
    if "items" in node:
        first = value[0] if isinstance(value, list) and value else None
        item = _fill(node["items"], name.rstrip("s"), first, f"One item of: {node.get('description') or name}", schemas)
        if not (isinstance(value, list) and value):
            value = [item]
    if isinstance(node.get("additionalProperties"), dict):
        _fill(node["additionalProperties"], name, None, f"Each value of: {node.get('description') or name}", schemas)
    for key in ("anyOf", "oneOf"):
        for i, sub in enumerate(node.get(key, [])):
            _fill(sub, name, None, f"Option {i + 1} of: {node.get('description') or name}", schemas)
    node.setdefault("example", value)
    return value


def _plain_refs(spec: dict) -> None:
    """APIMatic reads `allOf: [$ref]` plus nullable or a default as an inline schema. Where nothing is
    lost, point straight at the named schema: an optional field can simply be left out, and a query
    parameter's default goes into its description."""
    def single_ref(node: dict) -> str | None:
        parts = node.get("allOf", [])
        return parts[0]["$ref"] if len(parts) == 1 and "$ref" in parts[0] else None

    for schema in spec["components"]["schemas"].values():
        required = set(schema.get("required", []))
        for key, prop in schema.get("properties", {}).items():
            if key not in required and (ref := single_ref(prop)):
                schema["properties"][key] = {"$ref": ref}
    for item in spec["paths"].values():
        for op in item.values():
            for param in op.get("parameters", []):
                if ref := single_ref(param.get("schema", {})):
                    if "default" in param["schema"]:
                        param["description"] = f"{param.get('description', '').rstrip('.')}. Default: {param['schema']['default']}."
                    param["schema"] = {"$ref": ref}


def _examples_and_bodies(spec: dict) -> None:
    schemas = spec["components"]["schemas"]
    for name, schema in schemas.items():
        if "enum" in schema:
            schema.setdefault("example", schema["enum"][0])
            continue
        _fill(schema, name, schema.get("example"), SCHEMAS.get(name), schemas)

    for item in spec["paths"].values():
        for op in item.values():
            op_id = op.get("operationId", "")
            if not op.get("description"):
                op["description"] = OPERATIONS.get(op_id) or f"{op.get('summary', op_id)}."
            for param in op.get("parameters", []):
                schema = param.setdefault("schema", {})
                target = _resolve(schema, schemas)
                value = PARAM_EXAMPLES.get(param["name"], target.get("default", target.get("example")))
                if value is None:
                    value = _example_value(param["name"], target, schemas)
                param.setdefault("example", value)
                if "$ref" not in schema:
                    _fill(schema, param["name"], value, param.get("description"), schemas)
            body = op.get("requestBody")
            if body:
                for media in body.get("content", {}).values():
                    target = _resolve(media.get("schema", {}), schemas)
                    body.setdefault("description", target.get("description") or f"Request body for {op_id}.")
                    media.setdefault("example", _fill(media.setdefault("schema", {}), op_id, None,
                                                      target.get("description") or "Request body.", schemas))
            for code, response in op.get("responses", {}).items():
                for media in response.get("content", {}).values():
                    schema = media.setdefault("schema", {})
                    target = _resolve(schema, schemas)
                    text = target.get("description") or response.get("description")
                    if schema.get("type") == "array":
                        text = f"List of: {_resolve(schema.get('items', {}), schemas).get('description') or response.get('description')}"
                    media.setdefault("example", _fill(schema, op_id, None, text, schemas))
            if "responses" in op:
                op["responses"] = dict(sorted(op["responses"].items(), key=lambda kv: (not kv[0].isdigit(), kv[0])))


# --- applying it ----------------------------------------------------------------------------

SUBSCHEMA_KEYS = ("items", "additionalProperties", "not")
SUBSCHEMA_LISTS = ("anyOf", "oneOf", "allOf", "prefixItems")


def _drop_titles(schema: Any) -> None:
    """Remove the per-field titles FastAPI adds ("Project Id", "Currency"...). They repeat across the
    spec and APIMatic flags every repeat (rule L663); the descriptions say what each field is."""
    if not isinstance(schema, dict):
        return
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        _drop_titles(prop)
    for key in SUBSCHEMA_KEYS:
        _drop_titles(schema.get(key))
    for key in SUBSCHEMA_LISTS:
        for sub in schema.get(key, []):
            _drop_titles(sub)




def document(spec: dict) -> dict:
    spec["info"]["contact"] = CONTACT
    spec["info"]["license"] = LICENSE
    spec["tags"] = TAGS
    components = spec.setdefault("components", {})
    for name, description in SECURITY.items():
        if name in components.get("securitySchemes", {}):
            components["securitySchemes"][name].setdefault("description", description)

    schemas = components.get("schemas", {})
    for name, schema in schemas.items():
        title = schema.get("title")
        _drop_titles(schema)
        if title:  # a named schema keeps its own title; they are unique
            schema["title"] = title
        if name in SCHEMAS:
            schema.setdefault("description", SCHEMAS[name])
        for field, prop in schema.get("properties", {}).items():
            text = SCHEMA_FIELDS.get((name, field)) or FIELDS.get(field)
            if text:
                prop.setdefault("description", text)
        if "properties" in schema and "example" not in schema and "examples" not in schema:
            schema["example"] = EXAMPLES.get(name) or _object_example(schema, schemas)

    error_ref = {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorOut"}}}
    for item in spec.get("paths", {}).values():
        for op in item.values():
            for param in op.get("parameters", []):
                _drop_titles(param.get("schema"))
                if param["name"] in PARAMS:
                    param.setdefault("description", PARAMS[param["name"]])
            for media in op.get("requestBody", {}).get("content", {}).values():
                _drop_titles(media.get("schema"))
            for code, response in op.get("responses", {}).items():
                if code[0] in "45" and "content" not in response and "ErrorOut" in schemas:
                    response["content"] = copy.deepcopy(error_ref)
                for media in response.get("content", {}).values():
                    _drop_titles(media.get("schema"))

    _hoist_enums(spec)
    converted = _to_30({k: v for k, v in spec.items() if k != "openapi"})
    spec.clear()
    spec.update({"openapi": "3.0.3", **converted})
    _plain_refs(spec)
    _examples_and_bodies(spec)
    return spec
