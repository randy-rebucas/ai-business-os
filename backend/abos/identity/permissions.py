"""Single source of truth for workspace authorization (ADR-004). Routers check permissions, never role names.

Roles administer the workspace; they are not business titles ("CEO" is `membership.job_title` and grants nothing).
Permissions for later phases are declared now so the map stays the one place to read.
"""

ORG_ROLES = ("owner", "admin", "manager", "member", "viewer")

_VIEWER = {
    "org.read", "company.read", "knowledge.read", "agent.read", "task.read", "report.read", "notification.read",
}
_MEMBER = _VIEWER | {"knowledge.upload", "knowledge.ask", "agent.request"}
_MANAGER = _MEMBER | {
    "company.write", "knowledge.review", "agent.configure", "task.manage", "simulation.run", "rule.review",
    # Business records (invoices, payments, expenses, drafts) and the execution evidence that quotes them.
    "records.read", "records.manage",
}
_ADMIN = _MANAGER | {
    "org.members.manage", "audit.read", "agent.hire", "integration.manage", "usage.read",
    "knowledge.confidential",  # see/retrieve documents classified confidential
}
_OWNER = _ADMIN | {
    "org.manage", "org.members.manage_owners", "org.delete",
    "org.export",  # a full archive includes confidential documents and the audit log
    # Approving agent configurations, activation and sensitive actions is the CEO-level decision (SPEC step 5).
    "approval.decide", "agent.activate",
}

ORG_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset(_VIEWER),
    "member": frozenset(_MEMBER),
    "manager": frozenset(_MANAGER),
    "admin": frozenset(_ADMIN),
    "owner": frozenset(_OWNER),
}


def org_role_has(role: str | None, permission: str) -> bool:
    return role is not None and permission in ORG_PERMISSIONS.get(role, frozenset())
