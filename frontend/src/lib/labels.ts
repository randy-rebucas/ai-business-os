import type {
  AccessLevel, AnswerStatus, ConfigStatus, DocStatus, LifecycleStatus, OrgRole, PermissionMode, RuleStatus, SectionStatus,
} from "@/lib/types";

export type Tone = "success" | "info" | "warning" | "danger" | "neutral";

export const ROLE_LABEL: Record<OrgRole, string> = {
  owner: "Owner",
  admin: "Admin",
  manager: "Manager",
  member: "Member",
  viewer: "Viewer",
};

export const ROLE_HELP: Record<OrgRole, string> = {
  owner: "Full control, including approvals, agent activation and deleting the workspace.",
  admin: "Manages members, hires agents and reads the audit log.",
  manager: "Edits company information, reviews knowledge and configures agents.",
  member: "Uploads documents and asks questions.",
  viewer: "Read-only access.",
};

export const SECTION_TONE: Record<SectionStatus["status"], Tone> = {
  complete: "success",
  partial: "warning",
  missing: "neutral",
  skipped: "info",
};

export const SECTION_STATUS_LABEL: Record<SectionStatus["status"], string> = {
  complete: "Complete",
  partial: "Partly done",
  missing: "Missing",
  skipped: "Skipped for now",
};

export const DOC_STATUS: Record<DocStatus, { label: string; tone: Tone }> = {
  uploaded: { label: "Uploaded", tone: "neutral" },
  queued: { label: "Queued", tone: "neutral" },
  processing: { label: "Processing", tone: "info" },
  awaiting_review: { label: "Awaiting review", tone: "warning" },
  indexed: { label: "Indexed", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  superseded: { label: "Superseded", tone: "neutral" },
  archived: { label: "Archived", tone: "neutral" },
};

export const DOC_TYPES: [string, string][] = [
  ["policy", "Policy"], ["sop", "SOP"], ["handbook", "Handbook"], ["catalog", "Catalog"], ["pricing", "Price list"],
  ["contract", "Contract"], ["financial", "Financial report"], ["org_chart", "Org chart"],
  ["job_description", "Job description"], ["workflow", "Workflow"], ["script", "Script"], ["other", "Other"],
];
export const DOC_TYPE_LABEL: Record<string, string> = Object.fromEntries(DOC_TYPES);

export const ACCESS_LEVELS: [AccessLevel, string, string][] = [
  ["general", "General", "Everyone in the workspace and any authorised AI employee."],
  ["restricted", "Restricted", "Managers and above."],
  ["confidential", "Confidential", "Owners and admins only."],
];

export const ANSWER_STATUS: Record<AnswerStatus, { label: string; tone: Tone }> = {
  answered: { label: "Answered from sources", tone: "success" },
  insufficient_evidence: { label: "Not enough evidence", tone: "warning" },
  conflicting: { label: "Sources disagree", tone: "warning" },
  unsupported: { label: "Not grounded — don't rely on this", tone: "danger" },
};

export const PIPELINE_STEPS: [string, string][] = [
  ["processing", "Started"], ["fetched", "Fetched page"], ["extracted", "Text extracted"],
  ["chunked", "Split into sections"], ["embedded", "Embedded"], ["awaiting_review", "Indexed for review"],
];

export const LIFECYCLE: Record<LifecycleStatus, { label: string; tone: Tone }> = {
  available: { label: "Available", tone: "neutral" },
  selected: { label: "Selected", tone: "info" },
  configuring: { label: "Configuring", tone: "info" },
  awaiting_approval: { label: "Awaiting approval", tone: "warning" },
  testing: { label: "Testing", tone: "info" },
  ready_for_deployment: { label: "Ready for deployment", tone: "success" },
  active: { label: "Active", tone: "success" },
  paused: { label: "Paused", tone: "neutral" },
  failed: { label: "Failed", tone: "danger" },
  retired: { label: "Retired", tone: "neutral" },
};

export const CONFIG_STATUS: Record<ConfigStatus, { label: string; tone: Tone }> = {
  draft: { label: "Draft", tone: "info" },
  submitted: { label: "Waiting for approval", tone: "warning" },
  approved: { label: "Approved", tone: "success" },
  rejected: { label: "Changes requested", tone: "danger" },
  withdrawn: { label: "Withdrawn", tone: "neutral" },
};

export const MODE: Record<PermissionMode, { label: string; tone: Tone }> = {
  denied: { label: "Denied", tone: "neutral" },
  approval_required: { label: "Needs approval", tone: "warning" },
  auto: { label: "Automatic", tone: "success" },
};

export const RISK_TONE: Record<string, Tone> = { low: "neutral", medium: "info", high: "warning", critical: "danger" };

export const RULE_STATUS: Record<RuleStatus, { label: string; tone: Tone; help: string }> = {
  fact: { label: "Fact", tone: "neutral", help: "Stated in a source. Not enforced." },
  proposed: { label: "Proposed rule", tone: "info", help: "An interpretation that would change agent behaviour once confirmed." },
  unresolved: { label: "Open question", tone: "warning", help: "The sources don't answer it. Answer it to confirm a rule." },
  conflicting: { label: "Conflicting", tone: "danger", help: "Sources disagree. Pick the right version." },
  confirmed: { label: "Confirmed", tone: "success", help: "Used by AI employees." },
  rejected: { label: "Rejected", tone: "neutral", help: "Ignored." },
};

export const RULE_KIND: Record<string, string> = {
  policy: "Policy", workflow: "Procedure", responsibility: "Responsibility", approval: "Approval",
  threshold: "Threshold", customer_service: "Customer service", operating_hours: "Operating hours",
  escalation: "Escalation", reporting: "Reporting", objective: "Objective", recurring: "Recurring activity",
  dependency: "Dependency",
};

export const AGENT_SHORT: Record<string, string> = {
  executive: "Executive", sales: "Sales", finance: "Finance", marketing: "Marketing", operations: "Operations",
  procurement: "Procurement", hr: "HR", support: "Support",
};

export const DAY_LABEL: Record<string, string> = {
  mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun",
};

export const SCENARIO_CATEGORY: Record<string, string> = {
  normal: "Normal operations", missing_information: "Missing information", conflicting_policies: "Conflicting policies",
  outdated_documents: "Outdated documents", unauthorized_request: "Unauthorized request",
  insufficient_permissions: "Insufficient permissions", failed_integration: "Failed integration",
  transient_error: "Timeouts & transient errors", duplicate_execution: "Duplicate execution",
  financial_discrepancy: "Financial discrepancy", escalation: "Escalation", malicious_document: "Malicious document",
  cross_tenant: "Another organisation's data", approval_required: "Needs human approval",
};

export const DIMENSION_LABEL: Record<string, string> = {
  correctness: "Correctness", grounding: "Source grounding", policy_compliance: "Policy compliance",
  tool_selection: "Tool selection", tool_input_validity: "Tool input validity",
  permission_enforcement: "Permission enforcement", escalation: "Escalation behaviour", error_recovery: "Error recovery",
  output_format: "Output format", completion: "Completion criteria", overall: "Overall",
};

export const DECISION: Record<string, { label: string; tone: Tone }> = {
  executed: { label: "Ran", tone: "success" },
  blocked: { label: "Blocked", tone: "danger" },
  held_for_approval: { label: "Held for approval", tone: "warning" },
  rejected: { label: "Unknown tool", tone: "danger" },
  rejected_input: { label: "Invalid input", tone: "danger" },
  failed: { label: "Failed", tone: "danger" },
  duplicate_suppressed: { label: "Duplicate skipped", tone: "neutral" },
};

export const APPROVAL_SUBJECT: Record<string, string> = {
  agent_configuration: "Configuration", activation: "Activation (observation mode)",
  deployment_stage: "Full approved permissions", tool_action: "Agent action",
};

export function money(v: string | number | null | undefined, currency = "USD"): string {
  if (v == null) return "—";
  return `${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

/** "company.job-roles.updated" → "Job roles updated" */
export function auditActionLabel(action: string): string {
  const known: Record<string, string> = {
    "org.created": "Workspace created",
    "org.updated": "Workspace renamed",
    "org.member_added": "Member added",
    "org.member_updated": "Member updated",
    "org.member_removed": "Member removed",
    "company.profile_updated": "Company profile updated",
    "company.onboarding_completed": "Onboarding completed",
    "agents.hired": "AI employee hired",
    "agents.retired": "AI employee retired",
    "agents.config_generated": "Job description generated",
    "agents.config_edited": "Agent configuration edited",
    "agents.config_submitted": "Configuration submitted for approval",
    "approvals.approved": "Configuration approved",
    "approvals.rejected": "Changes requested on a configuration",
    "rules.extracted": "Business rules extracted",
    "rules.confirmed": "Business rule confirmed",
    "rules.rejected": "Business rule rejected",
    "rules.created": "Business rule added",
    "simulations.started": "Readiness tests started",
    "simulations.completed": "Readiness tests finished",
    "simulations.suggestion_applied": "Test suggestion applied",
    "simulations.scenario_created": "Test scenario added",
    "agents.activated": "AI employee activated",
    "agents.stage_widened": "AI employee given full permissions",
    "agents.paused": "AI employee paused",
    "agents.resumed": "AI employee resumed",
    "agents.config_rolled_back": "Configuration rolled back",
    "workflows.requested": "Task run requested",
    "workflows.completed": "Task run completed",
    "workflows.needs_review": "Task run needs review",
    "workflows.unverified": "Task run outcome unverified",
    "workflows.failed": "Task run failed",
    "workflows.cancelled": "Task run cancelled",
    "workflows.escalated": "Agent escalated to a person",
    "approvals.action_requested": "Agent action waiting for approval",
    "approvals.action_approved": "Agent action approved",
    "approvals.action_rejected": "Agent action rejected",
    "tools.reminder.send": "Payment reminder sent",
    "business.invoice_created": "Invoice recorded",
    "business.payment_recorded": "Payment recorded",
    "business.invoice_voided": "Invoice voided",
    "business.expense_submitted": "Expense submitted",
    "business.draft_discarded": "Draft discarded",
  };
  if (known[action]) return known[action];
  const parts = action.split(".");
  const noun = (parts.at(-2) ?? "").replaceAll("-", " ");
  const verb = parts.at(-1) ?? action;
  return `${noun.charAt(0).toUpperCase()}${noun.slice(1)} ${verb}`.trim();
}

// ---- Phase 5: execution ------------------------------------------------------------------------------------------

export const RUN_STATUS: Record<string, { label: string; tone: Tone; help: string }> = {
  queued: { label: "Queued", tone: "neutral", help: "Waiting for the worker (or for business hours)." },
  running: { label: "Running", tone: "info", help: "Executing step by step." },
  awaiting_approval: { label: "Awaiting approval", tone: "warning", help: "An action waits for a person's decision." },
  waiting_children: { label: "Waiting for agents", tone: "info", help: "Delegated agents are still working." },
  completed: { label: "Completed", tone: "success", help: "Every step finished and every check passed." },
  needs_review: { label: "Needs review", tone: "warning", help: "Finished, but something needs a person." },
  unverified: { label: "Unverified", tone: "danger", help: "An outcome is unknown — not counted as done." },
  failed: { label: "Failed", tone: "danger", help: "A step failed after its retries." },
  blocked: { label: "Blocked", tone: "danger", help: "The agent wasn't allowed to run." },
  cancelled: { label: "Cancelled", tone: "neutral", help: "Stopped by a person." },
  skipped: { label: "Skipped", tone: "neutral", help: "Not started (overlap or daily limit)." },
};

export const ACTIVE_RUN = ["queued", "running", "waiting_children"];

export const EXEC_STATUS: Record<string, { label: string; tone: Tone }> = {
  started: { label: "In flight", tone: "info" },
  succeeded: { label: "Succeeded", tone: "success" },
  unverified: { label: "Outcome unknown", tone: "danger" },
  failed: { label: "Failed", tone: "danger" },
  blocked: { label: "Blocked", tone: "danger" },
  held: { label: "Held for approval", tone: "warning" },
  refused: { label: "Refused by tool rule", tone: "warning" },
  rejected_input: { label: "Invalid input", tone: "danger" },
  unknown_tool: { label: "Unknown tool", tone: "danger" },
  unavailable: { label: "Not connected", tone: "neutral" },
  duplicate: { label: "Duplicate skipped", tone: "neutral" },
  rejected: { label: "Rejected by approver", tone: "neutral" },
};

export const TRIGGER_LABEL: Record<string, string> = {
  schedule: "Schedule", event: "Business event", on_demand: "On demand", delegated: "Delegated",
};

export const ACTION_STATUS: Record<string, { label: string; tone: Tone }> = {
  pending: { label: "Waiting", tone: "warning" },
  approved: { label: "Approved", tone: "success" },
  used: { label: "Approved · done", tone: "success" },
  rejected: { label: "Rejected", tone: "danger" },
  superseded: { label: "Superseded — changed", tone: "neutral" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export const INVOICE_STATE: Record<string, { label: string; tone: Tone }> = {
  open: { label: "Open", tone: "info" },
  overdue: { label: "Overdue", tone: "warning" },
  paid: { label: "Paid", tone: "success" },
  void: { label: "Void", tone: "neutral" },
};

export function totals(byCurrency: Record<string, string>): string {
  const parts = Object.entries(byCurrency).map(([c, v]) => money(v, c));
  return parts.length ? parts.join(" · ") : "—";
}
