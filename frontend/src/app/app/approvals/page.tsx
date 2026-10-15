"use client";

import { ArrowRight, Inbox } from "lucide-react";
import Link from "next/link";
import { useSWRConfig } from "swr";

import { ActionCard } from "@/components/execution/action-card";
import { ButtonLink } from "@/components/ui/button";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { useOrgData } from "@/lib/hooks";
import { APPROVAL_SUBJECT } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { ActionRequest, AgentListItem, ApprovalRecord, PendingApproval } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export default function ApprovalsPage() {
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const evidence = can("records.read");
  const actions = useOrgData<ActionRequest[]>(evidence ? "/api/v1/approvals/actions" : null);
  const pending = useOrgData<PendingApproval[]>("/api/v1/approvals/pending");
  const history = useOrgData<ApprovalRecord[]>("/api/v1/approvals");
  const agents = useOrgData<AgentListItem[]>("/api/v1/agents?include_retired=true");
  const names = Object.fromEntries((agents.data ?? []).map((a) => [a.id, a.name]));
  return (
    <>
      <PageHeader eyebrow="Governance" title="Approval inbox"
        description={can("approval.decide")
          ? "Agent actions and configurations waiting for your decision. An approval covers exactly what you see; if the action changes, it comes back here."
          : "Agent actions and configurations waiting for the owner's decision. Only owners can approve."} />
      {evidence && (
        <section aria-labelledby="actions-h" className="mb-10">
          <h2 id="actions-h" className="mb-3 text-sm font-semibold">Agent actions waiting</h2>
          {actions.error ? <ErrorState error={actions.error} /> : !actions.data ? <Spinner /> : actions.data.length === 0 ? (
            <p className="text-sm text-muted">No agent action is waiting. Actions appear here when an active agent wants to do something its configuration says needs a person.</p>
          ) : (
            <div className="space-y-3">
              {actions.data.map((a) => (
                <ActionCard key={a.id} req={a} canDecide={can("approval.decide")} onDecided={() => {
                  mutate(["/api/v1/approvals/actions", orgId]);
                  mutate(["/api/v1/approvals", orgId]);
                }} />
              ))}
            </div>
          )}
        </section>
      )}
      <section aria-labelledby="pending-h" className="mb-10">
        <h2 id="pending-h" className="mb-3 text-sm font-semibold">Configurations waiting</h2>
        {pending.error ? <ErrorState error={pending.error} /> : !pending.data ? <Spinner /> : pending.data.length === 0 ? (
          <EmptyState icon={Inbox} title="Nothing waiting">Configurations appear here when someone submits them for approval.</EmptyState>
        ) : (
          <div className="space-y-3">
            {pending.data.map((p) => (
              <Card key={p.config_id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <div>
                  <p className="font-medium text-fg">{p.agent_name} <span className="text-muted">· configuration v{p.version}</span></p>
                  <p className="text-xs text-muted">
                    {p.task_count} task{p.task_count === 1 ? "" : "s"} · submitted {p.submitted_at ? formatDateTime(p.submitted_at) : ""}{p.submitted_by && ` by ${p.submitted_by}`}
                  </p>
                </div>
                <ButtonLink href={`/app/approvals/${p.config_id}`} size="sm">{can("approval.decide") ? "Review & decide" : "View"} <ArrowRight /></ButtonLink>
              </Card>
            ))}
          </div>
        )}
      </section>
      <section aria-labelledby="history-h">
        <h2 id="history-h" className="mb-3 text-sm font-semibold">Decisions</h2>
        {history.error ? <ErrorState error={history.error} /> : !history.data ? <Spinner /> : history.data.length === 0 ? (
          <p className="text-sm text-muted">No decisions yet.</p>
        ) : (
          <Table label="Approval decisions">
            <thead><tr><th className={th}>Decision</th><th className={th}>Agent</th><th className={th}>By</th><th className={th}>When</th><th className={th}>Bound to</th></tr></thead>
            <tbody>
              {history.data.map((a) => (
                <tr key={a.id}>
                  <td className={td}>
                    <Badge tone={a.decision === "approved" ? "success" : "danger"}>{a.decision === "approved" ? "Approved" : a.subject_type === "tool_action" ? "Rejected" : "Changes requested"}</Badge> <span className="text-xs text-muted">{APPROVAL_SUBJECT[a.subject_type] ?? a.subject_type}</span>
                    {a.note && <p className="mt-1 max-w-xs text-xs text-muted">“{a.note}”</p>}
                  </td>
                  <td className={td}>{a.instance_id ? <Link href={`/app/agents/${a.instance_id}`} className="text-accent underline underline-offset-2">{names[a.instance_id] ?? "Agent"}</Link> : "—"} {a.subject_version != null && <span className="text-muted">v{a.subject_version}</span>}</td>
                  <td className={td}>{a.decided_by_name ?? "Former member"} <span className="text-xs text-muted">({a.decided_by_role})</span></td>
                  <td className={td}><span className="text-xs">{formatDateTime(a.created_at)}</span></td>
                  <td className={td}><span className="ident text-xs">{a.subject_hash.slice(0, 12)}<br />{a.policy_version}</span></td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>
    </>
  );
}
