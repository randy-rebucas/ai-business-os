"""Import every ORM model so Base.metadata is complete (used by Alembic and the app)."""

from abos.agents.models import AgentConfiguration, AgentDefinition, AgentInstance, TaskDefinition, TaskDependency
from abos.audit.models import AuditEvent
from abos.branding.models import WorkspaceBranding
from abos.business.models import Draft, Expense, Invoice, InvoiceLine, Payment
from abos.company.models import (
    BusinessObjective,
    BusinessProcess,
    CompanyLocation,
    CompanyProfile,
    Department,
    JobRole,
    Offering,
    OperationalChallenge,
    SoftwareSystem,
)
from abos.core.ratelimit import RateLimitBucket
from abos.governance.models import ActionRequest, Approval, BusinessRule
from abos.identity.models import (
    AuthenticationEvent,
    AuthToken,
    EmailOutbox,
    Organization,
    OrganizationMembership,
    User,
    UserSession,
)
from abos.knowledge.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    InterviewQuestion,
    JobRun,
    KnowledgeQuery,
    RagEvalCase,
    RagEvalResult,
    RagEvalRun,
)
from abos.llm.models import ModelUsage
from abos.notifications.models import Notification, NotificationDelivery, NotificationPreference
from abos.orchestration.models import WorkflowRun
from abos.privacy.models import OrganizationDeletion, OrgExport
from abos.reporting.models import DailyReport, ReportEvidence
from abos.simulation.models import SimulationResult, SimulationRun, SimulationScenario
from abos.tools.models import ExecutionReconciliation, ToolExecution

__all__ = [
    "AuditEvent", "AuthToken", "AuthenticationEvent", "BusinessObjective", "BusinessProcess", "CompanyLocation",
    "CompanyProfile", "Department", "EmailOutbox", "JobRole", "Offering", "OperationalChallenge", "Organization",
    "OrganizationMembership", "RateLimitBucket", "SoftwareSystem", "User", "UserSession",
    "Document", "DocumentChunk", "DocumentVersion", "InterviewQuestion", "JobRun", "KnowledgeQuery", "ModelUsage",
    "RagEvalCase", "RagEvalResult", "RagEvalRun",
    "AgentConfiguration", "AgentDefinition", "AgentInstance", "Approval", "BusinessRule", "TaskDefinition",
    "TaskDependency", "SimulationResult", "SimulationRun", "SimulationScenario",
    "ActionRequest", "Draft", "Expense", "Invoice", "InvoiceLine", "Payment", "ToolExecution", "WorkflowRun",
    "DailyReport", "ExecutionReconciliation", "Notification", "NotificationDelivery", "NotificationPreference",
    "ReportEvidence", "OrgExport", "OrganizationDeletion", "WorkspaceBranding",
]
