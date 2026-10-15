# CLAUDE MASTER PROMPT: AI BUSINESS OPERATING SYSTEM WITH MULTI-AGENT WORKFORCE AND RAG

## 1. ROLE AND MISSION

Act as a principal software architect, senior full-stack engineer, AI/LLM engineer, RAG specialist, multi-agent systems engineer, cybersecurity engineer, database architect, UI/UX designer, and SaaS product strategist.

Your mission is to design and implement a production-oriented **AI Business Operating System (AI Business OS)** that enables a business owner or CEO to onboard their company, hire specialized AI agents, teach those agents about the business through company documents and structured information, configure their responsibilities, test their readiness, deploy them under controlled permissions, and monitor their work through verifiable reports.

This must be a real, extensible SaaS application—not merely a chatbot, landing page, dashboard mockup, or collection of disconnected AI assistants.

The platform should behave like an AI workforce management system in which every agent has:

- A defined job description and area of expertise.
- Access to approved company knowledge through Retrieval-Augmented Generation (RAG).
- Explicit responsibilities, assignments, and operating schedules.
- Access to authorized business tools and integrations.
- Defined permissions, restrictions, and escalation rules.
- Testable performance criteria.
- An execution history and verifiable work evidence.
- Daily reporting and measurable performance metrics.

Build the system incrementally, ensuring that every implemented feature has functional backend logic, database persistence, appropriate validation, error handling, and tests.

Do not attempt to implement the entire platform in one uncontrolled generation. First inspect the existing project, establish the architecture, create an implementation plan, and then execute it in validated phases.

---

# 2. CORE PRODUCT CONCEPT

The platform is an AI-powered virtual company.

The CEO hires AI employees from a catalog of specialized agents. These agents learn the company's approved operating context, follow company-specific policies, execute authorized work, collaborate through an orchestrator, and report their results.

The application must follow this lifecycle:

**Discover Business → Select AI Employees → Ingest Knowledge → Configure Responsibilities → CEO Approval → Simulate and Test → Controlled Deployment → Execute Work → Report Results → Evaluate and Improve**

The system must not consider an agent operationally ready merely because it has received a prompt or been assigned documents.

An agent must pass defined readiness tests, have appropriate tool permissions, and receive the required authorization before accessing live execution capabilities.

## Core design principle

Separate the system into four distinct responsibilities:

1. **Business systems:** Store and process authoritative business records.
2. **RAG and knowledge services:** Retrieve relevant company information and approved policies.
3. **AI agents:** Interpret requests, analyze information, prepare plans, and invoke permitted tools.
4. **Governance and orchestration:** Coordinate execution, enforce permissions, require approvals, and record evidence.

AI models must not be the authoritative source of financial calculations, account balances, permissions, inventory quantities, or transaction status. These must come from validated business logic and authoritative data sources.

---

# 3. VALIDATED CEO ONBOARDING WORKFLOW

The initial implementation must center on the following onboarding experience.

## STEP 1 — COMPANY REGISTRATION AND CEO ONBOARDING

When a person registers a new organization, create a company workspace and assign the first authorized user the workspace Owner role.

The initial user may designate themselves as CEO during setup. Keep the administrative Owner role separate from the user's business title.

### Company onboarding interface

Build a guided, multi-step onboarding wizard.

Collect:

- Company name and legal or trading name.
- Industry and business category.
- Company description.
- Products and services.
- Target customers.
- Business locations and branches.
- Company size and organizational structure.
- Departments and existing job roles.
- Business objectives and KPIs.
- Operating days, hours, holidays, and time zone.
- Existing operational challenges.
- Current software and integrations.
- Existing business processes and approval procedures.
- Preferred reporting cadence and notification channels.
- Monthly AI workforce budget.

Include an AI-guided business interview that asks relevant follow-up questions based on the company's answers.

Do not force users to answer every question before proceeding. Mark missing information and let the system request additional context when needed.

### Business knowledge collection

Allow the CEO to upload company materials, including:

- PDF documents.
- DOCX documents.
- XLSX spreadsheets.
- CSV files.
- TXT and Markdown files.
- Supported text-based documents and website URLs.

Examples include:

- Employee handbooks.
- Standard operating procedures (SOPs).
- Company policies.
- Product and service catalogs.
- Pricing lists.
- Contracts and supplier documents.
- Customer service scripts.
- Financial reports.
- Organization charts.
- Job descriptions.
- Existing workflow documentation.

Display document upload progress, processing status, extracted content summaries, warnings, and indexing status.

Provide a review screen where the CEO can confirm that the extracted information accurately represents the business.

### Acceptance criteria

- The first organization user receives Owner permissions.
- Users cannot access another organization's data.
- Company information persists after refresh and login.
- Documents have persistent metadata and processing status.
- Failed document processing can be retried.
- The CEO can edit company information and upload additional documents later.

---

## STEP 2 — AI EMPLOYEE CATALOG AND TEAM SELECTION

Create an AI Employee Marketplace or Agent Catalog.

The CEO must be able to browse specialized agents, understand their expertise, select agents to hire, and configure the initial workforce.

Do not require the CEO to decide the correct number of agents without guidance.

Provide two modes:

1. **Recommended team:** The platform recommends an appropriate team based on the business profile, goals, workflows, and budget.
2. **Custom team:** The CEO manually selects the agents they want.

### Initial agent catalog

Implement the following agent definitions:

**A. Executive AI Agent — Virtual CEO Assistant**

Responsibilities:
- Analyze business performance.
- Summarize company operations.
- Coordinate other agents.
- Identify operational risks and opportunities.
- Prepare executive briefings.
- Track business objectives and KPIs.
- Recommend actions based on evidence.

The Executive Agent may coordinate work but must not automatically override business permissions or approve its own restricted actions.

**B. Sales and CRM Agent**

Responsibilities:
- Manage authorized CRM records.
- Qualify and categorize leads.
- Monitor sales opportunities.
- Identify overdue follow-ups.
- Prepare customer communications.
- Track conversion rates and pipeline performance.

**C. Finance and Accounting Agent**

Responsibilities:
- Analyze authorized financial records.
- Review invoices and receivables.
- Categorize expenses for review.
- Prepare financial summaries.
- Assist with reconciliation.
- Forecast cash flow using validated calculations.
- Identify discrepancies and unusual transactions.

It must not autonomously issue payments, alter posted financial entries, or submit tax filings without appropriate authorization.

**D. Marketing and Growth Agent**

Responsibilities:
- Develop marketing plans.
- Generate campaign drafts.
- Analyze campaign performance.
- Prepare social media and email content.
- Suggest customer segments and promotions.
- Coordinate approved campaign workflows.

External publication, paid advertising, and customer outreach must follow configured permissions.

**E. Operations and Project Management Agent**

Responsibilities:
- Manage tasks and assignments.
- Monitor deadlines and overdue work.
- Coordinate approved workflows.
- Identify bottlenecks.
- Track service-level agreements.
- Prepare operational summaries.

**F. Procurement and Inventory Agent**

Responsibilities:
- Analyze stock levels.
- Identify replenishment requirements.
- Analyze purchasing history.
- Compare supplier records.
- Prepare purchase recommendations and draft orders.

**G. HR and Workforce Agent**

Responsibilities:
- Answer questions using approved HR policies.
- Assist with onboarding.
- Track attendance exceptions.
- Summarize leave requests.
- Prepare workforce reports.

Consequential employment decisions must remain subject to human oversight.

**H. Customer Support Agent**

Responsibilities:
- Answer questions using approved company knowledge.
- Retrieve authorized order and service records.
- Classify customer inquiries.
- Prepare responses.
- Escalate complaints, disputes, and exceptional cases.

### Agent profile requirements

Every agent must have:

- Agent name and identity.
- Department and expertise.
- Role description.
- Responsibilities and prohibited activities.
- Required knowledge sources.
- Authorized business tools.
- Permissions and restrictions.
- Working schedule.
- Escalation conditions.
- KPIs and evaluation criteria.
- Reporting frequency.
- Model configuration.
- Usage budget.
- Current lifecycle status.

Agent definitions must be stored in the database, not hardcoded exclusively into frontend components.

### Agent lifecycle statuses

Implement explicit statuses such as:

- Available.
- Selected.
- Configuring.
- Awaiting Approval.
- Testing.
- Ready for Deployment.
- Active.
- Paused.
- Failed.
- Retired.

Do not allow an unapproved agent to access production execution tools.

---

## STEP 3 — RAG-POWERED BUSINESS KNOWLEDGE INGESTION

Retrieval-Augmented Generation (RAG) is a mandatory foundational feature.

The system must allow AI agents to answer questions and perform work using relevant, approved company information rather than relying solely on the language model's pretrained knowledge.

Do not describe document uploads as model training.

RAG retrieves relevant information at runtime. Model fine-tuning is not required for the MVP.

### Required RAG pipeline

Implement the following ingestion pipeline:

1. Accept and validate uploaded documents.
2. Store original files securely.
3. Extract text and structure.
4. Apply OCR to supported scanned documents.
5. Normalize text and preserve relevant tables and headings.
6. Classify documents by type and subject.
7. Split content into structure-aware chunks.
8. Generate embeddings.
9. Index embeddings and searchable text.
10. Attach source metadata and permissions.
11. Validate indexing results.
12. Make successfully indexed content available for authorized retrieval.

Use background jobs for potentially long-running document processing.

Track each document through statuses such as:

- Uploaded.
- Queued.
- Processing.
- Awaiting Review.
- Indexed.
- Failed.
- Superseded.
- Archived.

Support reprocessing and re-indexing when documents change.

### Recommended initial RAG stack

- PostgreSQL for structured data.
- pgvector for vector similarity search.
- PostgreSQL full-text search for keyword retrieval.
- An interchangeable embedding model provider.
- An interchangeable LLM provider.
- A document parser abstraction.
- OCR support for scanned documents.
- Optional reranking for improved retrieval relevance.

Implement hybrid retrieval that combines semantic similarity and keyword search.

Do not assume that vector similarity alone will retrieve exact product codes, invoice identifiers, policy thresholds, or other important business details reliably.

### Retrieval metadata

Each indexed chunk should include relevant metadata, such as:

- Organization ID.
- Document ID.
- Document title.
- Source type.
- Page number or section.
- Chunk identifier.
- Document version.
- Document classification.
- Approval status.
- Effective date, when applicable.
- Permissions and access classification.
- Indexing timestamp.

Enforce tenant isolation and access permissions during retrieval itself, not merely after the model receives the results.

### RAG query execution

For a user request:

1. Identify the requesting user, organization, and active agent.
2. Determine which knowledge sources the agent is permitted to access.
3. Transform the request into one or more retrieval queries.
4. Retrieve relevant content using authorized filters.
5. Combine semantic and keyword results.
6. Optionally rerank results.
7. Evaluate retrieval relevance and sufficiency.
8. Supply the relevant evidence to the model.
9. Require source-grounded responses for policy-dependent claims.
10. Return an answer with citations to the retrieved documents.

If evidence is insufficient or conflicting, the agent must disclose uncertainty and request clarification or escalate the issue.

Never invent document citations, page numbers, policy provisions, or retrieved facts.

### RAG evaluation

Implement a knowledge evaluation interface with:

- Test questions and expected answers.
- Expected source documents.
- Retrieval relevance scores.
- Citation validation.
- Unsupported-claim checks.
- Retrieval failure analysis.
- Comparison of indexing and retrieval configurations.

Include test cases for outdated documents, conflicting policies, inaccessible documents, missing information, and prompt injection within uploaded files.

---

## STEP 4 — BUSINESS RULE EXTRACTION AND AGENT JOB DESIGN

After document ingestion, the system should analyze the company profile, indexed knowledge, and approved source materials.

The objective is to generate proposed operating plans for each selected AI employee.

### Extract proposed business rules

Identify:

- Company policies.
- SOPs and workflows.
- Roles and responsibilities.
- Approval requirements.
- Spending and transaction thresholds.
- Customer service procedures.
- Operating hours.
- Escalation conditions.
- Reporting requirements.
- Performance objectives.
- Recurring activities.
- Dependencies between departments.

Distinguish explicitly between:

1. Facts extracted from documents.
2. Proposed interpretations.
3. Confirmed business rules.
4. Unresolved questions.
5. Conflicting or outdated information.

Do not silently convert ambiguous document content into enforced rules.

### Generate an agent job description

For every selected agent, generate a structured configuration containing:

- Job title.
- Department.
- Mission.
- Scope of responsibility.
- Included tasks.
- Excluded tasks.
- Required business knowledge.
- Permitted data sources.
- Authorized tools.
- Operating schedule.
- Task triggers.
- Task frequency.
- Priority rules.
- Dependencies.
- Escalation policies.
- Approval requirements.
- Success metrics.
- Reporting requirements.
- Usage limits.

### Task and workflow generation

Generate proposed tasks from the company information.

Each task should contain:

- Task title and description.
- Assigned agent.
- Trigger condition.
- Frequency or schedule.
- Required inputs.
- Expected output.
- Completion criteria.
- Dependencies.
- Priority.
- Deadline or service-level target.
- Applicable policy references.
- Required permissions.
- Approval requirements.
- Failure and retry behavior.

Example:

Agent: Finance Agent.

Task: Review outstanding invoices.

Trigger: Weekdays at 4 PM in the company's configured time zone.

Inputs: Authorized accounting records and approved payment policies.

Actions:
- Retrieve outstanding invoices.
- Identify overdue balances.
- Categorize follow-up priority.
- Draft reminders where permitted.
- Escalate discrepancies.

Output: An invoice review report with source references and task execution evidence.

Approval: Required before sending external communications if the organization has not explicitly authorized automatic sending.

The generated configuration must be editable before activation.

---

## STEP 5 — CEO REVIEW AND CONFIGURATION APPROVAL

Build a dedicated review screen for each proposed agent.

The CEO must be able to inspect and approve:

- Job description.
- Responsibilities.
- Task assignments.
- Business knowledge access.
- Operating schedule.
- Available tools.
- Permissions.
- Escalation rules.
- Performance metrics.
- Reporting cadence.
- Usage budget.
- Proposed automation level.

### Operating modes

Support these modes:

**24/7 Monitoring**

The agent responds to supported events and handles eligible tasks at any time.

**Business Hours**

The agent performs routine work during configured business hours.

**Scheduled Execution**

The agent runs selected tasks at specified times.

**Event-Driven Execution**

The agent activates when an event occurs, such as an invoice becoming overdue or a new support ticket arriving.

**On-Demand Execution**

The agent runs only when explicitly requested by an authorized user.

Separate monitoring schedules from execution schedules.

An agent may detect an event after hours but wait until the next business day to perform a routine action.

Critical alerts may be delivered immediately according to the organization's escalation policy.

### Permissions and approval model

Use explicit permission scopes for:

- Reading business data.
- Creating draft records.
- Modifying permitted records.
- Sending external communications.
- Creating transactions.
- Approving transactions.
- Executing financial operations.
- Accessing sensitive documents.

Apply risk-based authorization.

Routine read-only tasks may execute automatically after activation. Sensitive actions must require appropriate authorization.

Approval must be enforced by the backend, not just by hiding frontend buttons.

Record the approving user, decision, timestamp, relevant policy version, and scope of authorization.

---

## STEP 6 — SCENARIO SIMULATION AND READINESS TESTING

Before deployment, the system must test each agent against representative business scenarios.

This is a required feature, not a future enhancement.

### Scenario categories

Include:

1. Normal business operations.
2. Missing information.
3. Conflicting business policies.
4. Outdated documents.
5. Unauthorized requests.
6. Insufficient permissions.
7. Failed integrations.
8. Timeouts and transient errors.
9. Duplicate task execution.
10. Financial discrepancies.
11. Escalation scenarios.
12. Malicious instructions inside retrieved documents.
13. Attempts to access another organization's information.
14. Actions that require human approval.

### Example simulation

Agent: Customer Support Agent.

Scenario: A customer requests a refund exceeding the company's approved automatic refund threshold.

Expected behavior:

- Retrieve the applicable approved refund policy.
- Retrieve authorized order information.
- Verify the request against available records.
- Explain the applicable rule with source references.
- Prepare a refund request if appropriate.
- Escalate for approval.
- Never execute a prohibited refund.

### Test evaluation

Evaluate:

- Correctness.
- Source grounding.
- Policy compliance.
- Tool selection.
- Tool input validity.
- Permission enforcement.
- Escalation behavior.
- Error recovery.
- Output format.
- Completion criteria.

Use deterministic assertions wherever possible. Do not rely solely on an LLM judge.

Store test scenarios, expected outcomes, execution traces, scores, failures, and configuration versions.

### Deployment gate

An agent must not be marked Ready for Deployment until it passes its required acceptance tests.

The CEO must approve the production activation.

Support draft-only or observation mode as the initial deployment stage. Enable broader execution permissions only after successful validation.

When an agent fails, explain what failed, suggest specific configuration changes, and allow the CEO to refine and rerun the test.

---

## STEP 7 — CONTROLLED AGENT EXECUTION

Implement a real multi-agent orchestration system.

The Executive Agent acts as a coordinator, but specialized agents remain responsible for their own domain tasks.

Use a stateful orchestration framework such as LangGraph or an equivalent explicit workflow engine if justified by the implementation.

Do not implement uncontrolled recursive agent-to-agent conversations.

### Orchestration responsibilities

- Interpret the incoming request.
- Identify the objective.
- Determine which agents and tools are relevant.
- Create an execution plan.
- Check permissions and dependencies.
- Dispatch tasks.
- Collect results.
- Validate outputs.
- Handle failures and retries.
- Request approvals when needed.
- Consolidate results.
- Record the complete execution history.

### Agent collaboration

Example:

The CEO requests a revenue improvement analysis.

The Executive Agent delegates analysis to:

- Sales Agent: lead conversion and pipeline performance.
- Finance Agent: revenue, margins, and expenses.
- Marketing Agent: acquisition and campaign performance.
- Operations Agent: fulfillment delays and service bottlenecks.

Each agent retrieves relevant business knowledge through RAG and retrieves live records from authorized business services.

The Executive Agent combines the results, checks consistency, identifies missing evidence, and prepares recommendations.

It must not invent findings to fill gaps in the available data.

### Tool execution

Implement an agent tool registry.

Each tool definition must include:

- Tool name.
- Description.
- Input schema.
- Output schema.
- Required permissions.
- Validation rules.
- Risk classification.
- Approval requirements.
- Timeout.
- Retry policy.
- Audit requirements.

Use structured inputs and outputs.

Prevent agents from executing arbitrary SQL, unrestricted shell commands, or unapproved external actions.

Use validated business APIs for all mutations.

Implement idempotency keys where appropriate, task locking, bounded retries, and recovery behavior to prevent duplicate actions.

---

## STEP 8 — DAILY REPORTING AND CEO NOTIFICATIONS

Every agent must provide a daily report based on its actual task and execution records.

Reports must not be generated solely from the model's unverified recollection.

### Daily report structure

Each report should contain:

1. Agent name and reporting period.
2. Assigned tasks.
3. Completed tasks.
4. In-progress tasks.
5. Failed tasks.
6. Blocked tasks.
7. Tasks awaiting approval.
8. Actions performed.
9. Verified execution outcomes.
10. Supporting evidence and source references.
11. Exceptions and risks.
12. Escalations.
13. Upcoming assignments.
14. Performance against KPIs.
15. Model and execution costs, where available.

Distinguish clearly between an attempted action and a successfully completed action.

A tool timeout must not be reported as a successful task. If the outcome is unknown, mark it as unverified until reconciled.

### CEO dashboard

Implement a central AI Workforce Control Center showing:

- Total agents.
- Active, paused, and failed agents.
- Tasks assigned and completed.
- Tasks awaiting approval.
- Overdue tasks.
- Failed workflows.
- Important escalations.
- Agent performance.
- AI usage costs.
- Recent activity.
- Upcoming work.

Include filters for agent, department, status, date, and priority.

### Notifications

Support configurable:

- In-app notifications.
- Email notifications.
- SMS notifications through a provider abstraction.

Provide daily digest schedules and immediate alerts for critical incidents.

Do not hardcode a single messaging provider.

Respect notification preferences, delivery limits, and time zones. Store delivery status and retry failed notifications safely.

---

# 4. CONTINUOUS EVALUATION AND IMPROVEMENT

Implement an ongoing agent lifecycle.

The platform must continuously monitor task outcomes, execution failures, policy compliance, and operational performance.

Provide the CEO with controls to:

- Pause an agent.
- Resume an agent.
- Modify its job description.
- Change schedules.
- Adjust permissions.
- Modify task assignments.
- Update knowledge sources.
- Re-run readiness tests.
- Review previous versions.
- Roll back approved configurations.
- Retire an agent.

Do not automatically rewrite critical business policies or grant additional permissions based on an agent's own recommendations.

Changes to material rules and sensitive configurations must follow an explicit approval workflow.

Maintain version history for:

- Agent configurations.
- Approved policies.
- Task definitions.
- Tool permissions.
- Evaluation suites.
- Deployment settings.

When a material change occurs, identify affected agents and require appropriate regression testing before reactivation.

---

# 5. SYSTEM ARCHITECTURE AND TECHNOLOGY STACK

Use a modular, maintainable architecture.

Prefer a modular monolith with well-defined service boundaries for the MVP rather than prematurely distributing everything into microservices.

## Frontend

- Next.js using the current stable release.
- React and TypeScript.
- Tailwind CSS.
- shadcn/ui.
- Responsive desktop-first dashboard with mobile support.
- Accessible components and forms.
- Server-side authentication checks where applicable.
- Typed API clients and clear loading, error, and empty states.

The visual experience should be professional, modern, and suitable for business owners and executives.

## Backend

- Python.
- FastAPI.
- Pydantic for request and response validation.
- SQLAlchemy or an equivalent established ORM.
- Alembic for database migrations.
- A modular business-service layer.
- Versioned REST APIs.
- OpenAPI documentation.

Keep AI orchestration separate from core business transaction logic.

## Database

Use PostgreSQL as the primary database.

Use pgvector for RAG vector search and PostgreSQL full-text search for lexical retrieval.

Model the following entities as appropriate:

- Organizations.
- Users.
- Memberships.
- Roles and permissions.
- Company profiles.
- Departments.
- Documents.
- Document versions.
- Document chunks.
- Knowledge sources.
- Policies.
- Policy versions.
- Agent definitions.
- Agent instances.
- Agent configurations.
- Agent permissions.
- Agent assignments.
- Tasks.
- Task dependencies.
- Workflow definitions.
- Workflow runs.
- Simulation scenarios.
- Evaluation results.
- Approvals.
- Tool definitions.
- Tool executions.
- Audit events.
- Notifications.
- Daily reports.
- Usage records.
- Integration credentials references.

Create appropriate foreign keys, constraints, indexes, timestamps, and migration scripts.

Avoid using one generic JSON document as the entire data model. Use relational tables for entities and relationships, with JSONB only where flexible configuration or structured metadata is appropriate.

## Background execution

Use Redis and a suitable background job system for:

- Document processing.
- Embedding generation.
- Scheduled tasks.
- Agent execution.
- Report generation.
- Notification delivery.
- Retryable integration jobs.

Do not keep an LLM request open for the entire duration of long-running workflows.

Implement persisted execution state, task timeouts, bounded retries, and recovery mechanisms.

## AI and model abstraction

Create a provider-independent LLM gateway.

Support configurable model providers and model selections for:

- General reasoning.
- Document analysis.
- Embedding generation.
- Optional reranking.
- Evaluation.

Keep API keys in secure server-side configuration or a secrets manager.

Do not expose model credentials to the browser.

Do not require training a foundation model for the MVP.

## Storage

Use S3-compatible object storage for original documents, generated reports, and attachments.

Keep object storage private by default.

Use short-lived signed access URLs or an authenticated download endpoint.

Validate file types and sizes, scan uploads where supported, and prevent unauthorized file access.

---

# 6. MULTI-TENANT SECURITY AND GOVERNANCE

Security is a foundational requirement.

Every business organization must have an isolated workspace.

Implement:

- Organization-scoped database access.
- Role-based access control.
- Document-level access controls.
- Agent-specific permission scopes.
- Secure session handling.
- Server-side authorization.
- Input validation.
- Rate limiting.
- Secret management.
- Audit logging.
- Secure file handling.
- Protection against cross-tenant data leakage.
- Safe external tool execution.
- Data retention and deletion controls.

Use PostgreSQL Row-Level Security where appropriate as defense in depth, alongside explicit application-level authorization.

Never assume a frontend-supplied organization ID, agent ID, or document ID is trustworthy.

### RAG security

Apply authorization filters before returning retrieved content to an agent.

Test for:

- Cross-tenant retrieval.
- Unauthorized document retrieval.
- Indirect prompt injection in documents.
- Attempts to reveal hidden prompts or credentials.
- Retrieval of obsolete or unapproved policies.
- Malicious instructions embedded in source material.

Treat retrieved documents as untrusted information. They must not override system instructions, security policies, or tool permissions.

### Human approval

Enforce approval requirements on the backend for sensitive operations.

Store the identity of the approving user and bind the approval to the specific action, parameters, and relevant policy version.

If the proposed action changes materially after approval, require a new approval.

### Financial safety

Financial calculations must use validated application logic.

Use database transactions, consistent accounting rules, and idempotency protections for financial operations.

Do not permit an AI agent to bypass transaction validation or directly manipulate accounting records without authorization.

---

# 7. USER INTERFACE AND REQUIRED PAGES

Build the following functional pages.

## Public and authentication

- Landing page.
- Sign-up.
- Login.
- Password recovery.
- Organization creation.

## Onboarding

- Company profile wizard.
- Guided business interview.
- Document upload and processing.
- Knowledge review.
- Recommended team selection.
- Agent catalog.
- Agent configuration.
- Business rule review.
- Approval summary.
- Scenario simulation.
- Deployment readiness checklist.

## Main application

- Executive dashboard.
- AI Workforce Control Center.
- Agent directory.
- Individual agent profile.
- Agent job description and settings.
- Task management.
- Task execution details.
- Simulation and evaluation center.
- Knowledge base.
- Document library.
- Policy registry.
- Approval inbox.
- Activity and audit logs.
- Daily reports.
- Notification center.
- Integrations.
- Usage and cost tracking.
- Company settings.
- Users, departments, roles, and permissions.

## Agent detail page

Every agent profile should provide tabs for:

- Overview.
- Job Description.
- Responsibilities.
- Assigned Tasks.
- Knowledge Sources.
- Tools and Permissions.
- Schedule.
- Test Results.
- Activity History.
- Reports.
- Performance.
- Configuration Versions.

All pages must connect to real backend data. Do not implement nonfunctional controls or fake dashboard statistics.

---

# 8. API AND INTEGRATION DESIGN

Build versioned REST endpoints with validated schemas and documented authorization requirements.

Organize APIs around:

- Authentication and organizations.
- Company profile.
- Documents and knowledge processing.
- RAG retrieval and evaluation.
- Agent catalog and configuration.
- Task assignments.
- Workflow execution.
- Simulation and evaluation.
- Approvals.
- Reports.
- Notifications.
- Audit logs.
- Integrations.
- Usage and billing foundations.

Expose an internal tool interface that agents use to invoke permitted business operations.

Do not expose unrestricted internal services directly to language models.

Implement external integration adapters with:

- OAuth or API-key handling where appropriate.
- Secure credential storage.
- Explicit scopes.
- Timeouts.
- Retries with backoff.
- Rate-limit handling.
- Webhook validation.
- Idempotent processing where appropriate.
- Integration health status.

Initially implement a small number of functional tools rather than dozens of superficial connectors.

---

# 9. TESTING AND QUALITY ASSURANCE

Create automated tests from the beginning.

## Unit tests

Test:

- Business services.
- Policy validation.
- Permission checks.
- Task state transitions.
- Schedule calculations.
- Document metadata processing.
- Financial calculations.
- Agent configuration validation.

## Integration tests

Test:

- Authentication and organization isolation.
- Database transactions.
- Document ingestion.
- RAG retrieval.
- Tool execution.
- Approval workflows.
- Scheduled jobs.
- Notification delivery.
- Agent orchestration.

## End-to-end tests

Test the following complete journey:

1. A new user creates an organization.
2. The user completes the company profile.
3. The user uploads a business policy document.
4. The document is processed and indexed.
5. The CEO selects a Finance Agent.
6. The platform proposes a job description and tasks.
7. The CEO reviews and approves the configuration.
8. The agent runs a simulation.
9. The simulation passes the required acceptance tests.
10. The CEO activates the agent.
11. The agent executes an authorized read-only finance task.
12. The system records its tool results and task evidence.
13. The daily report is generated from those records.
14. The CEO can inspect the report and trace its claims to supporting evidence.

Add tests proving that one organization cannot retrieve another organization's documents or access its agents.

### RAG quality tests

Evaluate:

- Retrieval precision and relevance.
- Source citation correctness.
- Correct handling of conflicting policies.
- Correct handling of insufficient evidence.
- Retrieval permission enforcement.
- Resistance to prompt injection.
- Performance after document updates.

### Acceptance standards

Define measurable test thresholds for each agent type and use case. Do not assume one universal score guarantees readiness.

A passing readiness test must include mandatory security and authorization checks, regardless of the overall quality score.

---

# 10. DEVELOPMENT STRATEGY AND EXECUTION RULES

Work in the following phases.

## Phase 0 — Existing Project Inspection and Architecture

Before modifying code:

1. Inspect the repository and existing files.
2. Identify the current framework, dependencies, database, and implementation status.
3. Identify reusable components and existing functionality.
4. Identify architectural gaps and security risks.
5. Produce an implementation plan.
6. Define the initial database schema and major API contracts.
7. Establish development, testing, and environment configuration.

If a project already exists, preserve useful working functionality. Do not overwrite existing work blindly.

If starting from an empty repository, initialize the project with the proposed stack.

## Phase 1 — Working SaaS Foundation

Implement:

- Authentication.
- Organization creation.
- Initial Owner role.
- Organization-scoped authorization.
- Company profile.
- Database migrations.
- Basic application shell.
- Audit event infrastructure.

Validate the implementation before continuing.

## Phase 2 — Business Knowledge and RAG

Implement:

- Document uploads.
- Secure file storage.
- Document parsing.
- Background ingestion jobs.
- Chunking and embeddings.
- PostgreSQL full-text and vector retrieval.
- Tenant-scoped RAG.
- Source citations.
- Knowledge review.
- Basic RAG evaluation.

Demonstrate a working question-answering flow over an uploaded business document.

## Phase 3 — Agent Catalog and Configuration

Implement:

- Agent catalog.
- Agent definitions.
- Agent instances.
- Job description generation.
- Proposed task generation.
- Operating schedules.
- Permission configuration.
- CEO review and approval.
- Agent lifecycle state management.

## Phase 4 — Simulation and Evaluation

Implement:

- Scenario creation.
- Scenario execution.
- Expected outcomes.
- Test results.
- Failure analysis.
- Configuration refinement.
- Readiness checks.
- Deployment approval.

## Phase 5 — Controlled Execution

Implement:

- Agent orchestration.
- Tool registry.
- A limited set of real business tools.
- Task scheduling.
- Background execution.
- Approval enforcement.
- Retry and failure handling.
- Execution evidence.
- Audit trails.

Start with read-only and draft-only operations before introducing external side effects.

## Phase 6 — Reporting and Notifications

Implement:

- Activity records.
- Daily reports.
- Task completion verification.
- CEO dashboard metrics.
- In-app notifications.
- Email notification adapter.
- SMS adapter interface.
- Usage and cost tracking.

## Phase 7 — Hardening and Production Readiness

Implement:

- Comprehensive automated tests.
- Security review.
- Tenant isolation tests.
- Error monitoring.
- Observability.
- Rate limiting.
- Backup and recovery procedures.
- Data retention controls.
- Deployment documentation.
- Performance and cost optimization.

After each phase, run relevant tests and resolve failures before progressing.

Do not claim a feature is implemented unless it is actually functional and verified.

---

# 11. REQUIRED PROJECT DELIVERABLES

Produce and maintain:

1. A clear architecture document.
2. A phased implementation plan.
3. Database schema and migrations.
4. API documentation.
5. A documented RAG ingestion and retrieval pipeline.
6. Agent definitions and configuration schemas.
7. A reusable agent tool registry.
8. A scenario simulation and evaluation framework.
9. Security and authorization documentation.
10. Automated unit, integration, and end-to-end tests.
11. Environment variable documentation and an example configuration file without secrets.
12. Local development setup instructions.
13. Docker-based development environment where appropriate.
14. Deployment instructions.
15. A documented backup and recovery strategy.
16. A list of implemented features, remaining work, and known limitations.

Use clean modular code, type checking, consistent naming, structured logging, and explicit error handling.

Avoid giant files, duplicated business logic, unnecessary abstractions, and excessive dependencies.

Do not store API secrets in source code or commit real credentials.

Do not use fake AI responses to simulate successful operations in production code. Mocks are acceptable in automated tests when clearly separated from real implementations.

If a required provider credential is unavailable, implement the adapter, provide a clear configuration requirement, and test it with appropriate mocks. Do not claim live integration success without verification.

---

# 12. INITIAL MVP SUCCESS CRITERIA

The MVP is considered functional when the following end-to-end scenario works:

A CEO registers a company, completes the business profile, uploads an SOP, and selects an AI employee.

The platform indexes the SOP using RAG, extracts proposed rules, generates an editable job description and task assignments, and asks the CEO to approve them.

The CEO configures the agent's schedule and permissions, runs a realistic test scenario, reviews the results, and activates the agent after it passes the required checks.

The agent then performs an authorized task using the approved business knowledge and actual available tools.

The platform records the execution, validates the result, generates a daily report with supporting evidence, and delivers the report through the configured notification channel.

The CEO can inspect the agent's work, identify failures, change its configuration, rerun tests, and pause the agent.

All organization data remains isolated, and every sensitive action is subject to backend-enforced authorization.

This complete vertical slice is more important than implementing a large number of incomplete agents.

---

# 13. FINAL INSTRUCTIONS TO CLAUDE

Begin by inspecting the existing project or initializing the repository if it is empty.

Then:

1. Explain the proposed architecture and key design decisions.
2. Identify the initial MVP boundaries.
3. Produce a phased implementation checklist.
4. Identify security-critical decisions and database entities.
5. Implement Phase 1.
6. Run its tests and report the actual results.
7. Continue phase by phase, preserving working functionality and fixing regressions.

Prioritize correctness, maintainability, security, and real end-to-end functionality over the number of features generated.

Do not skip RAG. Do not replace backend behavior with static frontend demonstrations. Do not treat AI-generated text as verified execution evidence. Do not let agents bypass approval rules or access data outside their authorized scope.

When making architectural tradeoffs, explain the reasoning briefly and choose the simplest reliable solution that supports the long-term multi-agent SaaS design.

**The end goal is a real AI Business OS where a CEO can onboard a company, configure a specialized AI workforce, establish approved business knowledge through RAG, validate agents through realistic simulations, authorize their work, and monitor verifiable business outcomes from one unified application.**