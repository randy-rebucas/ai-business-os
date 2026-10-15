"use client";

import Link from "next/link";

import { Alert, Badge, Card, CardHeader, Meta, Table, td, th } from "@/components/ui/display";
import { useOrgData } from "@/lib/hooks";
import { CONFIG_STATUS, DAY_LABEL, LIFECYCLE, MODE, money, RISK_TONE } from "@/lib/labels";
import { DOC_TYPE_LABEL } from "@/lib/labels";
import type {
  AgentConfigDoc, AgentConfiguration, AgentDefinition, AgentTask, ConfigIssue, ConfigStatus, LifecycleStatus,
  PermissionMode, PolicyVocabulary, TaskSchedule,
} from "@/lib/types";

export function usePolicy() {
  return useOrgData<PolicyVocabulary>("/api/v1/agents/policy");
}

export function LifecycleBadge({ status }: { status: LifecycleStatus }) {
  return <Badge tone={LIFECYCLE[status].tone}>{LIFECYCLE[status].label}</Badge>;
}

export function ConfigBadge({ status }: { status: ConfigStatus }) {
  return <Badge tone={CONFIG_STATUS[status].tone}>{CONFIG_STATUS[status].label}</Badge>;
}

export function ModeBadge({ mode }: { mode: PermissionMode }) {
  return <Badge tone={MODE[mode].tone}>{MODE[mode].label}</Badge>;
}

export function scheduleLabel(s: TaskSchedule): string {
  if (s.kind === "monthly") return `Monthly on day ${s.day} at ${s.time}`;
  const days = s.days.join(",");
  const span = days === "mon,tue,wed,thu,fri" ? "Weekdays" : days === "mon,tue,wed,thu,fri,sat,sun" ? "Every day"
    : s.days.map((d) => DAY_LABEL[d]).join(", ");
  return `${span} at ${s.time}`;
}

export function triggerLabel(t: Pick<AgentTask, "trigger_type" | "schedule" | "event">, events?: PolicyVocabulary["events"]): string {
  if (t.trigger_type === "schedule" && t.schedule) return scheduleLabel(t.schedule);
  if (t.trigger_type === "event") return `When: ${events?.find((e) => e.key === t.event)?.label ?? t.event}`;
  return "Only when someone asks";
}

export function IssueList({ issues }: { issues: ConfigIssue[] }) {
  if (!issues.length) return null;
  const errors = issues.filter((i) => i.severity === "error");
  const warnings = issues.filter((i) => i.severity === "warning");
  return (
    <div className="space-y-3">
      {errors.length > 0 && (
        <Alert tone="danger" title={`${errors.length} problem${errors.length > 1 ? "s" : ""} to fix before approval`}>
          <ul className="list-disc space-y-1 pl-4">{errors.map((i, n) => <li key={n}>{i.message}</li>)}</ul>
        </Alert>
      )}
      {warnings.length > 0 && (
        <Alert tone="warning" title={`${warnings.length} thing${warnings.length > 1 ? "s" : ""} to check`}>
          <ul className="list-disc space-y-1 pl-4">{warnings.map((i, n) => <li key={n}>{i.message}</li>)}</ul>
        </Alert>
      )}
    </div>
  );
}

export function Bullets({ items, empty = "None" }: { items: string[]; empty?: string }) {
  if (!items.length) return <p className="text-sm text-subtle">{empty}</p>;
  return <ul className="list-disc space-y-1 pl-5 text-sm">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>;
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h3 className="text-xs font-medium uppercase tracking-wide text-subtle">{title}</h3>
      {children}
    </div>
  );
}

export function ResponsibilitiesView({ config }: { config: AgentConfigDoc }) {
  const j = config.job;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card><CardHeader title="Included work" /><div className="px-5 py-4"><Bullets items={j.included_tasks} /></div></Card>
      <Card><CardHeader title="Excluded — never does" /><div className="px-5 py-4"><Bullets items={j.excluded_tasks} /></div></Card>
      <Card><CardHeader title="Escalation policies" /><div className="px-5 py-4"><Bullets items={j.escalation_policies} /></div></Card>
      <Card><CardHeader title="Success metrics" /><div className="px-5 py-4"><Bullets items={j.success_metrics} /></div></Card>
    </div>
  );
}

export function JobView({ config }: { config: AgentConfigDoc }) {
  const j = config.job;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="lg:col-span-2">
        <CardHeader title={j.title} description={j.department} />
        <div className="space-y-4 px-5 py-4">
          <Block title="Mission"><p className="text-sm">{j.mission}</p></Block>
          {j.scope && <Block title="Scope of responsibility"><p className="text-sm">{j.scope}</p></Block>}
          <Block title="Required knowledge"><p className="text-sm">{j.required_knowledge.join(", ") || "—"}</p></Block>
        </div>
      </Card>
      <Card><CardHeader title="Approval requirements" /><div className="px-5 py-4"><Bullets items={j.approval_requirements} /></div></Card>
      <Card><CardHeader title="Priority rules" /><div className="px-5 py-4"><Bullets items={j.priority_rules} /></div></Card>
      <Card className="lg:col-span-2">
        <CardHeader title="Reporting & limits" />
        <dl className="grid gap-x-8 px-5 py-3 sm:grid-cols-2">
          <Meta label="Reporting">{config.reporting.cadence[0].toUpperCase() + config.reporting.cadence.slice(1)}</Meta>
          <Meta label="Monthly budget">{money(config.limits.monthly_budget_usd)}</Meta>
          <Meta label="Runs per day (max)">{config.limits.max_runs_per_day}</Meta>
          <Meta label="Model">{`${config.model.tier === "reasoning" ? "Reasoning" : "Fast"} · ${config.model.effort} effort`}</Meta>
          <Meta label="Dependencies">{j.dependencies.length ? j.dependencies.join("; ") : null}</Meta>
          {config.reporting.notes && <Meta label="Report notes">{config.reporting.notes}</Meta>}
        </dl>
      </Card>
    </div>
  );
}

export function TaskView({ task, events }: { task: AgentTask; events?: PolicyVocabulary["events"] }) {
  return (
    <Card className="px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-medium text-fg">{task.title}</h3>
          <p className="text-xs text-muted">{triggerLabel(task, events)}</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {task.priority !== "normal" && <Badge tone={task.priority === "low" ? "neutral" : "warning"}>{task.priority} priority</Badge>}
          {task.approval_required && <Badge tone="warning">Needs approval</Badge>}
        </div>
      </div>
      {task.description && <p className="mt-2 text-sm">{task.description}</p>}
      <dl className="mt-3 grid gap-x-8 sm:grid-cols-2">
        <Meta label="Inputs">{task.inputs.length ? task.inputs.join("; ") : null}</Meta>
        <Meta label="Expected output">{task.expected_output || null}</Meta>
        <Meta label="Done when">{task.completion_criteria.length ? task.completion_criteria.join("; ") : null}</Meta>
        <Meta label="Permissions">{task.required_permissions.join(", ") || null}</Meta>
        <Meta label="Depends on">{task.depends_on.length ? task.depends_on.join(", ") : null}</Meta>
        <Meta label="Service level">{task.sla_minutes ? `Within ${task.sla_minutes} min` : null}</Meta>
        <Meta label="On failure">{`Retry ${task.failure.max_retries}× every ${task.failure.retry_backoff_minutes} min, then ${task.failure.on_failure}`}</Meta>
        <Meta label="Policy references">{task.policy_refs.length ? `${task.policy_refs.length} confirmed rule(s)` : null}</Meta>
      </dl>
      {task.actions.length > 0 && (
        <div className="mt-2"><Block title="Steps"><ol className="list-decimal space-y-0.5 pl-5 text-sm">{task.actions.map((a, i) => <li key={i}>{a}</li>)}</ol></Block></div>
      )}
      {task.approval_reason && <p className="mt-2 text-xs text-warning">Approval: {task.approval_reason}</p>}
    </Card>
  );
}

export function PermissionsView({ config, definition, vocab }: { config: AgentConfigDoc; definition: AgentDefinition; vocab?: PolicyVocabulary }) {
  return (
    <div className="space-y-6">
      <Table label="Permission scopes">
        <thead><tr><th className={th}>Permission</th><th className={th}>Risk</th><th className={th}>This agent</th><th className={th}>Most it may ever have</th></tr></thead>
        <tbody>
          {(vocab?.scopes ?? []).map((s) => (
            <tr key={s.key}>
              <td className={td}>{s.label}<div className="ident text-xs text-subtle">{s.key}</div></td>
              <td className={td}><Badge tone={RISK_TONE[s.risk]}>{s.risk}</Badge></td>
              <td className={td}><ModeBadge mode={config.permissions[s.key]} /></td>
              <td className={td}><ModeBadge mode={definition.permission_ceilings[s.key]} /></td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Card>
        <CardHeader title="Authorised tools" description="Used only through the platform's tool registry once the agent is activated — never directly." />
        <ul className="divide-y divide-border">
          {definition.tools.map((t) => {
            const on = config.job.authorized_tools.includes(t.key);
            return (
              <li key={t.key} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm">
                <span>{t.label} <span className="ident text-xs text-subtle">{t.key}</span></span>
                <Badge tone={on ? "success" : "neutral"}>{on ? "Authorised" : "Not authorised"}</Badge>
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}

export function KnowledgeView({ config, generation }: { config: AgentConfigDoc; generation?: AgentConfiguration["generation"] }) {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="Knowledge access" description="Only approved (indexed) documents of these types and access levels can reach this agent." />
        <dl className="px-5 py-3">
          <Meta label="Document types">{config.knowledge.doc_types.map((t) => DOC_TYPE_LABEL[t] ?? t).join(", ") || null}</Meta>
          <Meta label="Access levels">{config.knowledge.access_levels.join(", ")}</Meta>
          <Meta label="Data sources">{config.job.data_sources.join("; ") || null}</Meta>
        </dl>
      </Card>
      {generation?.evidence && (
        <Card>
          <CardHeader title="Documents consulted when this was generated" />
          {generation.evidence.length ? (
            <ul className="divide-y divide-border">
              {generation.evidence.map((e) => (
                <li key={e.chunk_id} className="px-5 py-2.5 text-sm">
                  <Link href={`/app/knowledge/${e.document_id}`} className="text-accent underline underline-offset-2">{e.document_title}</Link>
                  {e.section && <span className="text-muted"> · {e.section}</span>}
                </li>
              ))}
            </ul>
          ) : <p className="px-5 py-4 text-sm text-muted">No approved document matched this agent&apos;s knowledge needs yet.</p>}
        </Card>
      )}
    </div>
  );
}

export function GenerationNotes({ generation }: { generation: AgentConfiguration["generation"] }) {
  if (!generation?.label && !generation?.warnings?.length && !generation?.adjustments?.length && !generation?.open_questions?.length) return null;
  return (
    <div className="space-y-3">
      {generation.label && <Alert tone={generation.is_dev ? "warning" : "info"} title={generation.is_dev ? "Development mode" : "How this was produced"}>{generation.label}</Alert>}
      {!!generation.adjustments?.length && <Alert tone="info" title="Fitted to your company"><Bullets items={generation.adjustments} /></Alert>}
      {!!generation.warnings?.length && <Alert tone="warning" title="Checks on the AI's text"><Bullets items={generation.warnings} /></Alert>}
      {!!generation.open_questions?.length && (
        <Alert tone="warning" title={`${generation.open_questions.length} business rule(s) still need review — not applied`}>
          <Bullets items={generation.open_questions.map((q) => q.title)} />
          <Link href="/app/rules" className="mt-1 inline-block underline underline-offset-2">Review business rules</Link>
        </Alert>
      )}
    </div>
  );
}
