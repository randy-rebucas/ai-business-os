// Mirrors backend Pydantic schemas (abos/*/schemas.py). Keep field names identical.

export type OrgRole = "owner" | "admin" | "manager" | "member" | "viewer";

export type User = {
  id: string;
  email: string;
  full_name: string;
  status: string;
  email_verified_at: string | null;
  created_at: string;
};

export type Organization = {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  deletion_scheduled_at: string | null;
};

// ---- workspace branding (abos/branding/schemas.py) ----
export type BrandMood = { key: string; label: string; display: string; text: string; description: string };
export type Branding = {
  logo_url: string | null;
  logo_width: number | null;
  logo_height: number | null;
  palette: { hex: string; share: number }[];
  logo_brand: string | null;
  accent: {
    source: "platform" | "logo" | "owner";
    brand: string;
    light: string;
    on_light: string;
    fill_light: string;
    on_fill_light: string;
    soft_light: string;
    dark: string;
    on_dark: string;
    fill_dark: string;
    on_fill_dark: string;
    soft_dark: string;
    marker: string;
    note_light: string;
    note_dark: string;
    adjusted: string[];
    contrast: Record<"light_on_ground" | "text_on_light" | "dark_on_ground" | "text_on_dark" | "marker_on_rail", number>;
  };
  mood: BrandMood;
  mood_source: "industry" | "owner";
  industry: string | null;
  moods: BrandMood[];
};

// ---- data controls (abos/privacy/schemas.py) ----
export type Retention = {
  notifications_days: number;
  ask_history_days: number;
  reports_days: number | null;
  kept: string[];
};

export type DeletionStatus = { scheduled_for: string | null; requested_by_id: string | null; grace_hours: number };

export type OrgExport = {
  id: string;
  status: "queued" | "building" | "ready" | "failed" | "expired";
  size_bytes: number | null;
  manifest: { tables?: Record<string, number>; files?: number };
  error: string | null;
  created_at: string;
  expires_at: string | null;
};

export type Membership = {
  organization: Organization;
  role: OrgRole;
  job_title: string | null;
  permissions: string[];
};

export type Me = { user: User; memberships: Membership[] };

export type Member = {
  user_id: string;
  email: string;
  full_name: string;
  role: OrgRole;
  job_title: string | null;
  status: string;
  joined_at: string;
};

export type SessionInfo = {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  ip: string | null;
  user_agent: string | null;
  current: boolean;
};

export type DayKey = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export type DayHours = { open: string; close: string };

export type CompanyProfile = {
  id: string;
  company_name: string;
  legal_name: string | null;
  trading_name: string | null;
  industry: string | null;
  business_category: string | null;
  description: string | null;
  target_customers: string | null;
  company_size: string | null;
  employee_count: number | null;
  organization_structure: string | null;
  timezone: string | null;
  operating_schedule: Partial<Record<DayKey, DayHours | null>> | null;
  holidays: { date: string; name: string }[];
  reporting_cadence: "daily" | "weekly" | "monthly" | null;
  notification_channels: { in_app?: boolean; email?: boolean; sms?: boolean };
  monthly_ai_budget: string | null;
  budget_currency: string;
  skipped_sections: string[];
  onboarding_completed_at: string | null;
  updated_at: string;
};

export type SectionKey =
  | "basics" | "offerings" | "customers" | "locations" | "structure" | "roles" | "objectives" | "operations"
  | "processes" | "software" | "challenges" | "reporting" | "budget";

export type SectionStatus = {
  key: SectionKey;
  label: string;
  status: "complete" | "partial" | "missing" | "skipped";
  missing: string[];
};

export type Completeness = { percent: number; sections: SectionStatus[]; missing_count: number };

export type CollectionItem = { id: string; created_at: string } & Record<string, unknown>;

// ---- knowledge (abos/knowledge/schemas.py) ----

export type DocStatus =
  | "uploaded" | "queued" | "processing" | "awaiting_review" | "indexed" | "failed" | "superseded" | "archived";
export type AccessLevel = "general" | "restricted" | "confidential";

export type DocWarning = { code: string; message: string };

export type DocumentRow = {
  id: string;
  title: string;
  source_type: "upload" | "url";
  source_url: string | null;
  original_filename: string | null;
  mime_type: string | null;
  status: DocStatus;
  doc_type: string;
  doc_type_source: "auto" | "reviewer";
  subject: string | null;
  access_level: AccessLevel;
  effective_date: string | null;
  summary: string | null;
  summary_label: string | null;
  warnings: DocWarning[];
  error_code: string | null;
  error_message: string | null;
  chunk_count: number;
  supersedes_document_id: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  indexed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type DocVersion = {
  id: string;
  version_no: number;
  sha256: string;
  size_bytes: number;
  mime_type: string;
  detected_format: string;
  scan_status: string;
  page_count: number | null;
  char_count: number | null;
  ocr_used: boolean;
  created_at: string;
};

export type JobInfo = {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  steps: { step: string; at: string; [k: string]: unknown }[];
  created_at: string;
  finished_at: string | null;
};

export type DocumentDetail = DocumentRow & {
  versions: DocVersion[];
  latest_job: JobInfo | null;
  superseded_by: { id: string; title: string; status: DocStatus }[];
};

export type Chunk = {
  id: string;
  chunk_index: number;
  section: string | null;
  page_number: number | null;
  kind: "text" | "table";
  content: string;
  flags: string[];
  token_count: number;
};

export type SearchHit = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  doc_type: string;
  access_level: AccessLevel;
  effective_date: string | null;
  version_no: number;
  section: string | null;
  page_number: number | null;
  content: string;
  score: number;
  vector_score: number | null;
  keyword_score: number | null;
  vector_rank: number | null;
  keyword_rank: number | null;
  flags: string[];
};

export type Citation = {
  source: string;
  chunk_id: string;
  document_id: string;
  document_title: string;
  section: string | null;
  page_number: number | null;
  version_no: number;
  quote: string;
};

export type AnswerStatus = "answered" | "insufficient_evidence" | "conflicting" | "unsupported";

export type Answer = {
  id: string;
  question: string;
  status: AnswerStatus;
  answer: string;
  citations: Citation[];
  conflicts: string[];
  follow_up_question: string | null;
  checks: { valid_citations: number; invalid_citations: { source: string; reason: string }[]; unsupported_numbers: string[]; downgraded_reasons: string[] };
  provider: string;
  model: string;
  label: string | null;
  sources: SearchHit[];
};

export type AiStatus = {
  llm: { provider: string; model: string; configured: boolean; dev_adapter: boolean };
  embeddings: { provider: string; configured: boolean; dimensions: number; dev_adapter: boolean };
};

export type EvalCase = {
  id: string;
  question: string;
  category: string;
  expected_status: string;
  expected_answer_contains: string[];
  expected_document_ids: string[];
  forbidden_document_ids: string[];
  forbidden_phrases: string[];
  access_levels: AccessLevel[];
  notes: string | null;
  created_at: string;
};

export type EvalCheck = { passed: boolean; detail: string };

export type EvalResult = {
  id: string;
  case_id: string | null;
  question: string;
  category: string;
  passed: boolean;
  status: string;
  answer: string;
  retrieved_document_ids: string[];
  reciprocal_rank: string;
  precision: string;
  checks: Record<string, EvalCheck>;
  failure_reasons: string[];
};

export type EvalRun = {
  id: string;
  config: { mode: string; top_k: number; llm_provider: string; embedding_provider: string; embedding_model: string };
  status: string;
  case_count: number;
  passed_count: number;
  metrics: {
    pass_rate: number;
    mrr: number | null;
    hit_rate: number | null;
    precision: number | null;
    citation_validity: number;
    security_failures: number;
    by_category: Record<string, { cases: number; passed: number }>;
  };
  created_at: string;
};

export type EvalRunDetail = EvalRun & { results: EvalResult[] };

export type InterviewQuestion = {
  id: string;
  topic_key: string;
  section: string;
  question: string;
  rationale: string | null;
  source: "rule" | "model" | "dev";
  status: "open" | "answered" | "dismissed";
  answer: string | null;
  answered_at: string | null;
  created_at: string;
};

// ---- agents & governance (abos/agents/schemas.py, abos/governance/schemas.py) ----

export type LifecycleStatus =
  | "available" | "selected" | "configuring" | "awaiting_approval" | "testing" | "ready_for_deployment" | "active"
  | "paused" | "failed" | "retired";
export type PermissionMode = "denied" | "approval_required" | "auto";
export type Scope =
  | "data.read" | "records.draft" | "records.modify" | "comms.external" | "transactions.create"
  | "transactions.approve" | "finance.execute" | "documents.sensitive";
export type Day = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

export type AgentTool = { key: string; label: string; scope: Scope };
export type TaskSchedule = { kind: "weekly"; days: Day[]; time: string } | { kind: "monthly"; day: number; time: string };
export type TaskTrigger = { type: "schedule" | "event" | "on_demand"; schedule?: TaskSchedule | null; event?: string | null };
export type FailurePolicy = { max_retries: number; retry_backoff_minutes: number; on_failure: "escalate" | "notify" | "skip" };

export type AgentDefinition = {
  id: string;
  key: string;
  version: number;
  letter: string;
  name: string;
  title: string;
  department: string;
  expertise: string[];
  role_description: string;
  responsibilities: string[];
  prohibited: string[];
  required_knowledge: string[];
  data_sources: string[];
  tools: AgentTool[];
  permission_ceilings: Record<Scope, PermissionMode>;
  escalation_conditions: string[];
  kpis: { name: string; target: string }[];
  reporting_frequency: string;
  default_operating_mode: string;
  default_automation: string;
  model: { tier: string; effort: string };
  default_monthly_budget_usd: string;
  supported_events: string[];
  task_templates: { key: string; title: string; description: string; trigger: TaskTrigger }[];
  status: LifecycleStatus;
  instance_id: string | null;
};

export type PolicyVocabulary = {
  scopes: { key: Scope; label: string; risk: "low" | "medium" | "high" | "critical"; max_mode: PermissionMode; default_mode: PermissionMode }[];
  events: { key: string; label: string }[];
  operating_modes: { key: string; label: string }[];
  automation_levels: { key: string; label: string }[];
  lifecycle: { key: LifecycleStatus; label: string }[];
};

export type RecommendationItem = {
  key: string;
  name: string;
  letter: string;
  score: number;
  recommended: boolean;
  reasons: string[];
  excluded_reason: string | null;
  estimated_monthly_usd: string;
  hired: boolean;
};

export type Recommendation = {
  items: RecommendationItem[];
  recommended_keys: string[];
  total_estimated_monthly_usd: string;
  budget: { amount: string | null; currency: string; status: "within" | "over" | "not_set" | "not_comparable"; message: string };
  profile_gaps: string[];
  method: string;
};

export type AgentConfigDoc = {
  job: {
    title: string;
    department: string;
    mission: string;
    scope: string;
    included_tasks: string[];
    excluded_tasks: string[];
    required_knowledge: string[];
    data_sources: string[];
    authorized_tools: string[];
    priority_rules: string[];
    dependencies: string[];
    escalation_policies: string[];
    approval_requirements: string[];
    success_metrics: string[];
  };
  reporting: { cadence: "daily" | "weekly" | "monthly"; notes: string };
  operating: {
    mode: "always_on" | "business_hours" | "scheduled" | "event_driven" | "on_demand";
    monitoring: "continuous" | "business_hours" | "off";
    execution_window: "business_hours" | "any_time";
    critical_alerts: "immediate" | "next_business_day";
  };
  permissions: Record<Scope, PermissionMode>;
  knowledge: { doc_types: string[]; access_levels: AccessLevel[] };
  model: { tier: "reasoning" | "fast"; effort: "low" | "medium" | "high" };
  limits: { monthly_budget_usd: string; max_runs_per_day: number };
  automation_level: "observe" | "draft" | "assisted" | "autonomous";
};

export type AgentTask = {
  id: string;
  key: string;
  position: number;
  title: string;
  description: string;
  trigger_type: TaskTrigger["type"];
  schedule: TaskSchedule | null;
  event: string | null;
  inputs: string[];
  actions: string[];
  expected_output: string;
  completion_criteria: string[];
  priority: "low" | "normal" | "high" | "critical";
  sla_minutes: number | null;
  policy_refs: string[];
  required_permissions: Scope[];
  approval_required: boolean;
  approval_reason: string | null;
  failure: FailurePolicy;
  depends_on: string[];
};

export type ConfigIssue = { severity: "error" | "warning"; field: string; message: string };

export type ConfigStatus = "draft" | "submitted" | "approved" | "rejected" | "withdrawn";

export type ConfigSummary = {
  id: string;
  instance_id: string;
  version: number;
  status: ConfigStatus;
  config_hash: string;
  source: "template" | "generated" | "edited";
  created_at: string;
  submitted_at: string | null;
  decided_at: string | null;
};

export type ConfigGeneration = {
  provider?: string;
  model?: string;
  label?: string;
  is_dev?: boolean;
  evidence?: { chunk_id: string; document_id: string; document_title: string; section: string | null }[];
  citations?: { chunk_id: string; document_id: string; document_title: string; quote: string }[];
  rules_used?: string[];
  open_questions?: { id: string; title: string; status: string }[];
  adjustments?: string[];
  warnings?: string[];
};

export type AgentConfiguration = ConfigSummary & {
  config: AgentConfigDoc;
  generation: ConfigGeneration;
  tasks: AgentTask[];
  issues: ConfigIssue[];
};

export type AgentInstance = {
  id: string;
  definition_key: string;
  name: string;
  status: LifecycleStatus;
  status_reason: string | null;
  status_changed_at: string;
  current_config_id: string | null;
  approved_config_id: string | null;
  deployment_stage: "observation" | "full" | null;
  activated_at: string | null;
  created_at: string;
};

export type AgentListItem = AgentInstance & {
  letter: string;
  department: string;
  current_version: number | null;
  current_config_status: ConfigStatus | null;
  task_count: number;
  monthly_budget_usd: string | null;
};

export type ApprovalRecord = {
  id: string;
  subject_type: string;
  subject_id: string;
  instance_id: string | null;
  subject_version: number | null;
  subject_hash: string;
  policy_version: string;
  decision: "approved" | "rejected";
  note: string | null;
  scope: Record<string, unknown>;
  decided_by_id: string | null;
  decided_by_name: string | null;
  decided_by_role: OrgRole;
  created_at: string;
};

export type AgentDetail = AgentInstance & {
  definition: AgentDefinition;
  current_config: AgentConfiguration | null;
  approvals: ApprovalRecord[];
  execution: { allowed: boolean; reason: string };
};

export type SchedulePreview = {
  timezone: string | null;
  execution_window: string;
  tasks: { key: string; title: string; trigger_type: string; event: string | null; schedule: TaskSchedule | null; next_runs: string[] }[];
  notes: string[];
};

export type PendingApproval = {
  config_id: string;
  instance_id: string;
  agent_name: string;
  definition_key: string;
  version: number;
  config_hash: string;
  submitted_at: string | null;
  submitted_by: string | null;
  task_count: number;
};

export type RuleStatus = "fact" | "proposed" | "unresolved" | "conflicting" | "confirmed" | "rejected";

export type BusinessRule = {
  id: string;
  kind: string;
  status: RuleStatus;
  title: string;
  statement: string;
  source_type: "document" | "interview" | "profile" | "manual";
  citations: { chunk_id: string; document_id: string; document_title: string; version_no: number; section: string | null; quote: string }[];
  source_ref: string | null;
  access_level: AccessLevel;
  applies_to: string[];
  threshold_amount: string | null;
  threshold_currency: string | null;
  conflicts_with: string[];
  resolution: string | null;
  provider: string;
  label: string | null;
  reviewed_at: string | null;
  created_at: string;
  stale: string | null;
};

export type RuleExtraction = {
  created: number;
  existing: number;
  conflicts: number;
  dropped: { statement: string; reason: string }[];
  provider: string;
  label: string | null;
  sources_considered: number;
};

// ---- simulation (abos/simulation/schemas.py) ----

export type Assertion = {
  type: string;
  dimension: string;
  label: string;
  mandatory: boolean;
  tool?: string;
  text?: string;
  passed?: boolean;
  detail?: string;
  [k: string]: unknown;
};

export type Scenario = {
  id: string;
  agent_key: string;
  key: string;
  version: number;
  category: string;
  title: string;
  description: string;
  input: { request?: string; question?: string; duplicate?: boolean; task?: string };
  fixtures: Record<string, unknown>;
  scripted_plan: { tool: string; input: unknown }[];
  assertions: Assertion[];
  expected_outcome: string;
  required: boolean;
  is_active: boolean;
  source: "library" | "custom";
};

export type DimensionScore = { passed: number; total: number; score: number | null };

export type SimulationRun = {
  id: string;
  instance_id: string;
  configuration_id: string;
  config_version: number;
  config_hash: string;
  policy_version: string;
  status: "queued" | "running" | "completed" | "error";
  passed: boolean | null;
  planner: { mode?: "scripted" | "model"; provider?: string; model?: string; label?: string | null };
  suite: { scenario_id: string; key: string; version: number; required: boolean }[];
  scores: Record<string, DimensionScore>;
  thresholds: Record<string, number>;
  summary: { scenarios?: number; passed?: number; mandatory_failures?: number; gate_reasons?: string[] };
  error: string | null;
  created_at: string;
  finished_at: string | null;
  agent_name: string | null;
};

export type TraceStep = {
  n: number;
  tool: string;
  input: unknown;
  trigger: string;
  scope?: string | null;
  decision: "executed" | "blocked" | "held_for_approval" | "rejected" | "rejected_input" | "failed" | "duplicate_suppressed";
  reason?: string;
  attempts?: number;
  result?: Record<string, unknown>;
};

export type Suggestion = { kind: string; text: string; applicable: boolean; [k: string]: unknown };

export type SimulationResult = {
  id: string;
  scenario_id: string | null;
  scenario_key: string;
  scenario_version: number;
  category: string;
  title: string;
  passed: boolean;
  mandatory_failed: boolean;
  outcome: "completed" | "escalated" | "incomplete";
  trace: TraceStep[];
  output: { status: string; answer: string; valid_citations: number; citations: Citation[]; redactions: number };
  assertions: Assertion[];
  analysis: { explanation?: string; suggestions?: Suggestion[] };
};

export type SimulationRunDetail = SimulationRun & { results: SimulationResult[]; progress: { step: string; key?: string }[] };

export type Readiness = {
  ready: boolean;
  items: { key: string; label: string; ok: boolean; detail: string }[];
  run_id: string | null;
  config_hash: string | null;
  status: LifecycleStatus;
  deployment_stage: "observation" | "full" | null;
};

export type AuditEvent = {
  id: string;
  actor_user_id: string | null;
  actor_type: string;
  actor_name: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  data: Record<string, unknown>;
  created_at: string;
};

// ---- Phase 5: execution ----------------------------------------------------------------------------------------

export type RunStatus = "queued" | "running" | "awaiting_approval" | "waiting_children" | "completed" | "needs_review"
  | "unverified" | "failed" | "blocked" | "cancelled" | "skipped";

export type WorkflowRun = {
  id: string;
  instance_id: string;
  agent_name: string | null;
  definition_key: string | null;
  configuration_id: string;
  config_version: number;
  config_hash: string;
  policy_version: string;
  task_key: string;
  task_title: string;
  trigger_type: "schedule" | "event" | "on_demand" | "delegated";
  trigger: { occurrence?: string; event?: string; subject_type?: string; subject_id?: string; parent_run_id?: string };
  request: string | null;
  parent_id: string | null;
  depth: number;
  status: RunStatus;
  status_reason: string | null;
  not_before: string | null;
  planner: { mode?: "playbook" | "model"; provider?: string; model?: string; label?: string | null };
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  summary: string;
  validation_passed: boolean | null;
};

export type ExecStatus = "started" | "succeeded" | "unverified" | "failed" | "blocked" | "held" | "refused"
  | "rejected_input" | "unknown_tool" | "unavailable" | "duplicate" | "rejected";

export type EvidenceRef = { type: string; id: string; label: string };

export type ToolExecution = {
  id: string;
  run_id: string;
  instance_id: string;
  step_no: number;
  tool: string;
  registry_version: string;
  scope: string | null;
  risk: string;
  input: unknown;
  input_hash: string;
  idempotency_key: string | null;
  decision: string;
  reason: string;
  status: ExecStatus;
  attempts: number;
  output: Record<string, unknown>;
  evidence: EvidenceRef[];
  approval_request_id: string | null;
  error: string | null;
  planner: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
};

export type ActionRequest = {
  id: string;
  run_id: string;
  instance_id: string;
  agent_name: string | null;
  task_title: string | null;
  step_no: number;
  tool: string;
  tool_label: string;
  scope: string | null;
  risk: string;
  parameters: Record<string, unknown>;
  params_hash: string;
  config_hash: string;
  policy_version: string;
  reason: string;
  status: "pending" | "approved" | "rejected" | "superseded" | "used" | "cancelled";
  note: string | null;
  decided_by_name: string | null;
  decided_by_role: string | null;
  decided_at: string | null;
  created_at: string;
};

export type Check = { label: string; ok: boolean; detail: string };

export type ChildRun = { run_id: string; agent: string; status: RunStatus; reason: string | null; summary: string;
  findings: unknown[]; missing_evidence: string[] };

export type WorkflowRunDetail = WorkflowRun & {
  steps: { n: number; tool: string; status: ExecStatus; decision: string; reason: string; execution_id: string; note: string }[];
  output: { summary?: string; findings?: (Record<string, unknown> | string)[]; missing_evidence?: string[]; label?: string | null };
  validation: { passed?: boolean; checks?: Check[] };
  error: string | null;
  executions: ToolExecution[];
  action_requests: ActionRequest[];
  children: ChildRun[];
  parent: { run_id: string; task_title: string } | null;
};

export type RunnableAgent = {
  instance_id: string;
  agent_name: string;
  definition_key: string;
  status: LifecycleStatus;
  deployment_stage: "observation" | "full" | null;
  can_run: boolean;
  reason: string;
  tasks: { key: string; title: string; trigger_type: string; event: string | null; schedule: TaskSchedule | null;
    required_permissions: string[] }[];
};

// ---- Phase 5: business records -----------------------------------------------------------------------------------

export type InvoiceState = "open" | "overdue" | "paid" | "void";

export type Invoice = {
  id: string;
  number: string;
  customer_name: string;
  customer_email: string | null;
  currency: string;
  issue_date: string;
  due_date: string;
  total: string;
  recorded_total: string | null;
  paid: string;
  balance: string;
  state: InvoiceState;
  days_overdue: number;
  aging: string;
  checks: string[];
  notes: string | null;
  source: string;
  created_at: string;
  lines: { id: string; position: number; description: string; quantity: string; unit_price: string; amount: string }[];
  payments: { id: string; amount: string; currency: string; received_on: string; method: string; reference: string | null }[];
};

export type Expense = {
  id: string;
  incurred_on: string;
  supplier: string;
  description: string;
  amount: string;
  currency: string;
  category: string | null;
  status: string;
  created_at: string;
};

export type Draft = {
  id: string;
  kind: "payment_reminder" | "briefing";
  subject: string;
  body: string;
  recipient: string | null;
  related_type: string | null;
  related_id: string | null;
  status: "draft" | "sent" | "discarded";
  instance_id: string | null;
  run_id: string | null;
  created_at: string;
  sent_at: string | null;
};

export type Receivables = {
  as_of: string;
  outstanding_by_currency: Record<string, string>;
  overdue_by_currency: Record<string, string>;
  counts: Record<InvoiceState, number>;
};

// ---- Phase 6: reports, notifications, control center, usage ------------------------------------------------------

export type RunItem = { run_id: string; task: string; trigger: string; status: RunStatus; reason: string | null;
  summary: string; finished_at: string | null };

export type DailyReport = {
  id: string;
  instance_id: string;
  agent_name: string | null;
  report_date: string;
  timezone: string;
  period_start: string;
  period_end: string;
  final: boolean;
  version: number;
  summary: string;
  counts: Record<string, number>;
  generated_at: string;
};

export type DailyReportDetail = DailyReport & {
  evidence: { section: string; ref_type: string; ref_id: string }[];
  content: {
    agent: { name: string; department: string; date: string; timezone: string; deployment_stage: string | null };
    assigned: { key: string; title: string; trigger: string; runs: number }[];
    completed: RunItem[];
    in_progress: RunItem[];
    failed: RunItem[];
    blocked: RunItem[];
    awaiting_approval: (RunItem | { request_id: string; run_id: string; action: string; reason: string; requested_at: string })[];
    actions: { per_tool: Record<string, { attempted: number; succeeded: number; unverified: number; failed: number; not_run: number }>;
      side_effects: { execution_id: string; run_id: string; tool: string; status: string; evidence: EvidenceRef[] }[] };
    outcomes: { attempted: number; completed: number; unverified: number; failed: number; not_run: number;
      reconciled: { execution_id: string; tool: string; outcome: string; detail: string }[];
      unverified_items: { execution_id: string; run_id: string; tool: string; reason: string }[] };
    evidence: { runs: number; tool_executions: number; action_requests: number; source_documents: string[] };
    exceptions: { run_id: string; task?: string; tool?: string; status: string; reason: string | null; failed_checks?: string[] }[];
    escalations: { execution_id: string; run_id: string; severity: string; reason: string }[];
    upcoming: { task: string; at: string; run_id?: string; deferred?: boolean }[];
    kpis: { measured: { name: string; value: string; basis: string }[];
      defined: { name: string; target: string; value: null; note: string }[] };
    costs: { model_calls: number; model_cost_usd: string; dev_calls: number; tool_executions: number; label: string | null };
  };
};

export type AppNotification = {
  id: string;
  kind: string;
  severity: "info" | "warning" | "critical";
  title: string;
  body: string;
  link: string | null;
  subject_type: string | null;
  subject_id: string | null;
  read_at: string | null;
  digested_at: string | null;
  created_at: string;
};

export type NotificationPrefs = {
  email_immediate: "off" | "warning" | "critical";
  email_digest: boolean;
  digest_time: string;
  sms_critical: boolean;
  sms_number: string | null;
  sms_provider: string;
};

export type NotificationDelivery = {
  id: string;
  notification_id: string | null;
  channel: "email" | "sms";
  kind: "alert" | "digest";
  provider: string;
  to_address: string;
  subject: string;
  status: string;
  attempts: number;
  next_attempt_at: string | null;
  last_error: string | null;
  sent_at: string | null;
  created_at: string;
};

export type CCItem = { run_id: string; agent: string | null; department: string | null; task: string; status: RunStatus;
  priority: string; trigger: string; created_at: string; overdue: boolean };

export type ControlCenter = {
  filters: { agent_id: string | null; department: string | null; status: string | null; date_from: string; date_to: string;
    priority: string | null; timezone: string };
  options: { agents: { id: string; name: string }[]; departments: string[] };
  agents: { total: number; active: number; paused: number; failed: number; by_status: Record<string, number> };
  tasks: Record<"assigned" | "completed" | "in_progress" | "awaiting_approval" | "pending_actions" | "overdue" | "failed"
    | "unverified" | "needs_review" | "blocked", number>;
  failed_workflows: CCItem[];
  escalations: { execution_id: string; run_id: string; agent: string | null; severity: string; reason: string; at: string }[];
  needs_retest: { instance_id: string; agent: string; status: LifecycleStatus; reasons: string[] }[];
  performance: { instance_id: string; agent: string; department: string; status: LifecycleStatus; runs: number;
    completed: number; failed: number; unverified: number; needs_review: number; completion_rate: number | null;
    avg_duration_seconds: number | null; overdue: number; cost_usd: string }[];
  costs: { total_usd: string; label: string };
  recent: CCItem[];
  upcoming: { agent: string | null; instance_id: string; task: string; at: string; priority: string; run_id?: string; deferred?: boolean }[];
  overdue: CCItem[];
};

export type AgentBudget = { instance_id: string; agent: string; budget_usd: string | null; spent_usd: string;
  remaining_usd: string | null; over: boolean };

export type UsageSummary = {
  from: string;
  to: string;
  timezone: string;
  total_cost_usd: string;
  calls: number;
  errors: number;
  dev_calls: number;
  dev_label: string | null;
  runs: number;
  tool_executions: number;
  by_agent: { instance_id: string | null; agent: string; calls: number; input_tokens: number; output_tokens: number; cost_usd: string }[];
  by_purpose: { purpose: string; calls: number; cost_usd: string }[];
  daily: { date: string; calls: number; cost_usd: string }[];
  month_to_date_usd: string;
  company_budget: { amount: string; currency: string; comparable: boolean; spent_usd: string; over: boolean } | null;
  agent_budgets: AgentBudget[];
  note: string;
};
