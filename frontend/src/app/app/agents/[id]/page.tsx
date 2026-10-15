"use client";

import { ArrowLeft, FileCheck2, Pencil, RotateCcw, Send, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";

import {
  ConfigBadge, GenerationNotes, IssueList, JobView, KnowledgeView, LifecycleBadge, PermissionsView, ResponsibilitiesView,
  TaskView, triggerLabel, usePolicy,
} from "@/components/agents/shared";
import { RunStatusBadge } from "@/components/execution/shared";
import { RunBadge } from "@/components/simulation/shared";
import { Button, ButtonLink } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, EmptyState, ErrorState, Meta, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Tabs } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { APPROVAL_SUBJECT, LIFECYCLE, money, TRIGGER_LABEL } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { AgentConfiguration, AgentDetail, ConfigSummary, ControlCenter, DailyReport, SchedulePreview, SimulationRun, WorkflowRun } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const JOURNEY = ["selected", "configuring", "awaiting_approval", "testing", "ready_for_deployment", "active"] as const;

function Journey({ status }: { status: AgentDetail["status"] }) {
  const at = JOURNEY.indexOf(status as (typeof JOURNEY)[number]);
  return (
    <ol aria-label="Lifecycle" className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
      {JOURNEY.map((s, i) => (
        <li key={s} aria-current={i === at ? "step" : undefined}
          className={i < at ? "text-fg" : i === at ? "font-semibold text-accent" : "text-subtle"}>
          {i + 1}. {LIFECYCLE[s].label}
        </li>
      ))}
    </ol>
  );
}

function Overview({ agent }: { agent: AgentDetail }) {
  const d = agent.definition;
  const last = agent.approvals[0];
  return (
    <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <div className="space-y-6">
        <Card>
          <CardHeader title="Lifecycle" description={agent.status_reason ?? undefined} />
          <div className="space-y-4 px-5 py-4">
            {agent.status === "retired" || agent.status === "failed" || agent.status === "paused"
              ? <LifecycleBadge status={agent.status} /> : <Journey status={agent.status} />}
            <Alert tone={agent.execution.allowed ? "success" : "neutral"} title={agent.execution.allowed ? "May execute work" : "Cannot execute work"}>
              {agent.execution.reason}. Execution requires an active agent whose current configuration you approved.
            </Alert>
          </div>
        </Card>
        <Card>
          <CardHeader title="About this agent" description={`${d.title} · catalog v${d.version}`} />
          <div className="px-5 py-4 text-sm">{d.role_description}</div>
        </Card>
      </div>
      <Card className="self-start">
        <CardHeader title="At a glance" />
        <dl className="px-5 py-3">
          <Meta label="Department">{d.department}</Meta>
          <Meta label="Hired">{formatDateTime(agent.created_at)}</Meta>
          <Meta label="Deployment">{agent.deployment_stage === "full" ? "Full approved permissions" : agent.deployment_stage === "observation" ? "Observation mode (read & draft only)" : "Not activated"}</Meta>
          <Meta label="Configuration">{agent.current_config ? <span className="flex flex-wrap items-center gap-2">v{agent.current_config.version} <ConfigBadge status={agent.current_config.status} /></span> : null}</Meta>
          <Meta label="Budget">{agent.current_config ? `${money(agent.current_config.config.limits.monthly_budget_usd)} / month` : null}</Meta>
          <Meta label="Last decision">{last ? `${last.decision === "approved" ? "Approved" : "Changes requested"} by ${last.decided_by_name ?? "a former member"}, ${formatDateTime(last.created_at)}` : null}</Meta>
        </dl>
      </Card>
    </div>
  );
}

function Schedule({ agent }: { agent: AgentDetail }) {
  const { data, error } = useOrgData<SchedulePreview>(agent.current_config ? `/api/v1/agents/${agent.id}/schedule` : null);
  const { data: vocab } = usePolicy();
  const op = agent.current_config!.config.operating;
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="Operating mode" />
        <dl className="px-5 py-3">
          <Meta label="Mode">{vocab?.operating_modes.find((m) => m.key === op.mode)?.label ?? op.mode}</Meta>
          <Meta label="Monitoring">{op.monitoring.replace("_", " ")}</Meta>
          <Meta label="Routine work">{op.execution_window === "business_hours" ? "Business hours only" : "Any time"}</Meta>
          <Meta label="Critical alerts">{op.critical_alerts === "immediate" ? "Immediately, at any hour" : "Next business day"}</Meta>
        </dl>
      </Card>
      {error ? <ErrorState error={error} /> : !data ? <Spinner /> : (
        <>
          {data.notes.map((n) => <p key={n} className="text-sm text-muted">{n}</p>)}
          <Table label="Upcoming runs">
            <thead><tr><th className={th}>Task</th><th className={th}>Trigger</th><th className={th}>Next runs ({data.timezone ?? "no time zone"})</th></tr></thead>
            <tbody>
              {data.tasks.map((t) => (
                <tr key={t.key}>
                  <td className={td}>{t.title}</td>
                  <td className={td}>{triggerLabel({ trigger_type: t.trigger_type as "schedule", schedule: t.schedule, event: t.event }, vocab?.events)}</td>
                  <td className={td}>
                    {t.next_runs.length ? (
                      <ul className="space-y-0.5 text-xs">{t.next_runs.map((r) => <li key={r}><time dateTime={r}>{data.timezone ? new Date(r).toLocaleString(undefined, { timeZone: data.timezone, dateStyle: "medium", timeStyle: "short" }) : r}</time></li>)}</ul>
                    ) : <span className="text-xs text-subtle">{t.trigger_type === "schedule" ? "No upcoming run inside the allowed window" : "—"}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </>
      )}
    </div>
  );
}

function Versions({ agent, onChange }: { agent: AgentDetail; onChange: () => void }) {
  const { can } = useSession();
  const { data, error } = useOrgData<ConfigSummary[]>(`/api/v1/agents/${agent.id}/config/versions`);
  const [busy, setBusy] = useState<number | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const approvedVersions = new Set(agent.approvals
    .filter((a) => a.decision === "approved" && a.subject_type === "agent_configuration").map((a) => a.subject_version));
  const restore = async (version: number) => {
    if (!confirm(`Start a new draft from version ${version}? It needs approval and testing again.`)) return;
    setBusy(version);
    setFailure(null);
    try {
      await api(`/api/v1/agents/${agent.id}/config/rollback`, { method: "POST", org: true, body: { version } });
      onChange();
    } catch (err) {
      setFailure(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="space-y-6">
      {error ? <ErrorState error={error} /> : !data ? <Spinner /> : data.length === 0 ? <p className="text-sm text-muted">No configuration yet.</p> : (
        <Table label="Configuration versions">
          <thead><tr><th className={th}>Version</th><th className={th}>Status</th><th className={th}>Source</th><th className={th}>Created</th><th className={th}>Fingerprint</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {data.map((v) => (
              <tr key={v.id}>
                <td className={td}>v{v.version}{v.id === agent.approved_config_id && <Badge tone="success" className="ml-2">Approved version</Badge>}</td>
                <td className={td}><ConfigBadge status={v.status} /></td>
                <td className={td}>{v.source}</td>
                <td className={td}><span className="text-xs">{formatDateTime(v.created_at)}</span></td>
                <td className={td}><span className="ident text-xs">{v.config_hash.slice(0, 12)}</span></td>
                <td className={td}>{can("agent.configure") && approvedVersions.has(v.version) && v.id !== agent.current_config_id && agent.status !== "retired" && (
                  <Button size="sm" variant="ghost" loading={busy === v.version} disabled={busy !== null} onClick={() => restore(v.version)}><RotateCcw /> Restore</Button>
                )}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {failure && <Alert tone="danger">{failure}</Alert>}
      <Card>
        <CardHeader title="Approval history" description="Each decision is bound to the exact configuration fingerprint and policy version." />
        {agent.approvals.length === 0 ? <p className="px-5 py-4 text-sm text-muted">No decisions yet.</p> : (
          <ul className="divide-y divide-border">
            {agent.approvals.map((a) => (
              <li key={a.id} className="space-y-1 px-5 py-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={a.decision === "approved" ? "success" : "danger"}>{a.decision === "approved" ? "Approved" : "Changes requested"}</Badge> <span className="text-xs text-muted">{APPROVAL_SUBJECT[a.subject_type] ?? a.subject_type}</span>
                  <span>v{a.subject_version} by {a.decided_by_name ?? "a former member"} ({a.decided_by_role})</span>
                  <time className="text-xs text-subtle" dateTime={a.created_at}>{formatDateTime(a.created_at)}</time>
                </div>
                {a.note && <p className="text-muted">“{a.note}”</p>}
                <p className="ident text-xs text-subtle">config {a.subject_hash.slice(0, 12)} · {a.policy_version}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function TestResults({ agent }: { agent: AgentDetail }) {
  const { data, error } = useOrgData<SimulationRun[]>(`/api/v1/agents/${agent.id}/simulations`);
  if (error) return <ErrorState error={error} />;
  if (!data) return <Spinner />;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">Readiness tests run in a sandbox. <Link href={`/app/agents/${agent.id}/readiness`} className="text-accent underline underline-offset-2">Readiness &amp; deployment</Link></p>
      {data.length === 0 ? <p className="text-sm text-muted">No test runs yet.</p> : (
        <Table label="Test results">
          <thead><tr><th className={th}>Started</th><th className={th}>Configuration</th><th className={th}>Result</th><th className={th}>Scenarios</th><th className={th}>Security failures</th></tr></thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.id}>
                <td className={td}><Link href={`/app/simulations/runs/${r.id}`} className="text-accent underline underline-offset-2">{formatDateTime(r.created_at)}</Link></td>
                <td className={td}>v{r.config_version}</td>
                <td className={td}><RunBadge run={r} /></td>
                <td className={td}>{r.summary.scenarios ? `${r.summary.passed} / ${r.summary.scenarios}` : "—"}</td>
                <td className={td}>{r.summary.mandatory_failures ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}

function Activity({ agent }: { agent: AgentDetail }) {
  const { data, error } = useOrgData<WorkflowRun[]>(`/api/v1/workflows?agent_id=${agent.id}&limit=50`);
  if (error) return <ErrorState error={error} />;
  if (!data) return <Spinner />;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">Real task runs, newest first. Each links to its execution evidence. <Link href="/app/tasks" className="text-accent underline underline-offset-2">All tasks</Link></p>
      {data.length === 0 ? <p className="text-sm text-muted">No task has run yet.</p> : (
        <Table label="Activity history">
          <thead><tr><th className={th}>Started</th><th className={th}>Task</th><th className={th}>Trigger</th><th className={th}>Status</th></tr></thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.id}>
                <td className={td}><span className="text-xs">{formatDateTime(r.started_at ?? r.created_at)}</span></td>
                <td className={td}><Link href={`/app/tasks/${r.id}`} className="text-accent underline underline-offset-2">{r.task_title}</Link></td>
                <td className={td}><span className="text-xs">{TRIGGER_LABEL[r.trigger_type] ?? r.trigger_type}</span></td>
                <td className={td}><RunStatusBadge status={r.status} /></td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}

function Reports({ agent }: { agent: AgentDetail }) {
  const { can } = useSession();
  const { data, error } = useOrgData<DailyReport[]>(can("report.read") ? `/api/v1/reports?agent_id=${agent.id}` : null);
  if (!can("report.read")) return <p className="text-sm text-muted">You don&apos;t have access to reports.</p>;
  if (error) return <ErrorState error={error} />;
  if (!data) return <Spinner />;
  if (data.length === 0) return <p className="text-sm text-muted">No daily report yet. Reports start the day after activation.</p>;
  return (
    <ul className="divide-y divide-border rounded-lg border border-border">
      {data.map((r) => (
        <li key={r.id} className="px-4 py-3 text-sm">
          <Link href={`/app/reports/${r.id}`} className="font-medium text-accent underline underline-offset-2">{r.report_date}</Link>
          {!r.final && <Badge tone="info" className="ml-2">So far</Badge>}
          <p className="mt-1 text-muted">{r.summary}</p>
        </li>
      ))}
    </ul>
  );
}

function Performance({ agent }: { agent: AgentDetail }) {
  const { data, error } = useOrgData<ControlCenter>(`/api/v1/dashboard?agent_id=${agent.id}`);
  if (error) return <ErrorState error={error} />;
  if (!data) return <Spinner />;
  const p = data.performance[0];
  if (!p) return <p className="text-sm text-muted">No data.</p>;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">Last 7 days ({data.filters.date_from} – {data.filters.date_to}), from execution records.</p>
      <dl className="rounded-lg border border-border px-4 py-2">
        <Meta label="Runs">{p.runs}</Meta>
        <Meta label="Completed">{p.completed}</Meta>
        <Meta label="Completion rate">{p.completion_rate == null ? "—" : `${Math.round(p.completion_rate * 100)}%`}</Meta>
        <Meta label="Needs review">{p.needs_review}</Meta>
        <Meta label="Failed / unknown">{`${p.failed} / ${p.unverified}`}</Meta>
        <Meta label="Over SLA">{p.overdue}</Meta>
        <Meta label="Average duration">{p.avg_duration_seconds == null ? "—" : `${p.avg_duration_seconds}s`}</Meta>
        <Meta label="AI cost">{`${p.cost_usd} USD`}</Meta>
      </dl>
      <p className="text-sm"><Link href="/app/control-center" className="text-accent underline underline-offset-2">Control Center</Link></p>
    </div>
  );
}

function Actions({ agent, onChange }: { agent: AgentDetail; onChange: () => void }) {
  const { can } = useSession();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cfg = agent.current_config;
  const run = async (key: string, path: string, body?: unknown) => {
    setBusy(key);
    setError(null);
    try {
      await api(path, { method: "POST", org: true, body });
      onChange();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };
  if (agent.status === "retired") return null;
  const errors = cfg?.issues.filter((i) => i.severity === "error").length ?? 0;
  const configure = can("agent.configure");
  return (
    <div className="mb-6 space-y-3">
      <div className="flex flex-wrap gap-2">
        {configure && (!cfg || cfg.status !== "submitted") && (
          <Button variant={cfg ? "secondary" : "primary"} loading={busy === "gen"} disabled={!!busy}
            onClick={() => (!cfg || cfg.status !== "draft" || confirm("Replace the current draft with a newly generated one?")) && run("gen", `/api/v1/agents/${agent.id}/config/generate`)}>
            <Sparkles /> {cfg ? "Regenerate" : "Generate job description & tasks"}
          </Button>
        )}
        {configure && cfg && <ButtonLink href={`/app/agents/${agent.id}/configure`} variant="secondary"><Pencil /> Edit configuration</ButtonLink>}
        {configure && cfg?.status === "draft" && (
          <Button loading={busy === "submit"} disabled={!!busy || errors > 0} onClick={() => run("submit", `/api/v1/agents/${agent.id}/config/submit`)}>
            <Send /> Submit for approval
          </Button>
        )}
        {cfg?.status === "submitted" && can("approval.decide") && (
          <ButtonLink href={`/app/approvals/${cfg.id}`}><FileCheck2 /> Review & decide</ButtonLink>
        )}
        {cfg && <ButtonLink href={`/app/agents/${agent.id}/readiness`} variant="secondary"><ShieldCheck /> Readiness &amp; deployment</ButtonLink>}
        {can("agent.hire") && (
          <Button variant="danger" disabled={!!busy} loading={busy === "retire"}
            onClick={() => confirm(`Retire ${agent.name}? It keeps its history but can't be configured again.`) && run("retire", `/api/v1/agents/${agent.id}/retire`, {})}>
            Retire
          </Button>
        )}
      </div>
      {cfg?.status === "draft" && errors > 0 && <p className="text-xs text-muted">Fix the problems below to submit for approval.</p>}
      {cfg?.status === "submitted" && <Alert tone="warning" title="Waiting for the CEO's approval">Editing now creates a new version and withdraws this one.</Alert>}
      {cfg?.status === "approved" && <Alert tone="success" title="Configuration approved">{agent.status === "testing" ? "Next: run the readiness tests. " : ""}Editing creates a new version that needs approval and testing again.</Alert>}
      {cfg?.status === "rejected" && agent.approvals[0]?.note && <Alert tone="danger" title="Changes requested">{agent.approvals[0].note}</Alert>}
      {error && <Alert tone="danger">{error}</Alert>}
    </div>
  );
}

function tabsFor(agent: AgentDetail, cfg: AgentConfiguration | null, onChange: () => void, events?: { key: string; label: string }[]) {
  const vocabTabs = cfg ? [
    { key: "job", label: "Job description", content: <JobView config={cfg.config} /> },
    { key: "responsibilities", label: "Responsibilities", content: <ResponsibilitiesView config={cfg.config} /> },
    { key: "tasks", label: "Assigned tasks", badge: <Badge>{cfg.tasks.length}</Badge>, content: (
      <div className="space-y-4">{cfg.tasks.length ? cfg.tasks.map((t) => <TaskView key={t.id} task={t} events={events} />) : <p className="text-sm text-muted">No tasks.</p>}</div>
    ) },
    { key: "knowledge", label: "Knowledge sources", content: <KnowledgeView config={cfg.config} generation={cfg.generation} /> },
    { key: "permissions", label: "Tools & permissions", content: <PermissionsWrapper agent={agent} cfg={cfg} /> },
    { key: "schedule", label: "Schedule", content: <Schedule agent={agent} /> },
    { key: "tests", label: "Test results", content: <TestResults agent={agent} /> },
    { key: "activity", label: "Activity history", content: <Activity agent={agent} /> },
    { key: "reports", label: "Reports", content: <Reports agent={agent} /> },
    { key: "performance", label: "Performance", content: <Performance agent={agent} /> },
  ] : [];
  return [{ key: "overview", label: "Overview", content: <Overview agent={agent} /> }, ...vocabTabs,
    { key: "versions", label: "Configuration versions", content: <Versions agent={agent} onChange={onChange} /> }];
}

function PermissionsWrapper({ agent, cfg }: { agent: AgentDetail; cfg: AgentConfiguration }) {
  const { data: vocab } = usePolicy();
  return <PermissionsView config={cfg.config} definition={agent.definition} vocab={vocab} />;
}

export default function AgentProfilePage() {
  const { id } = useParams<{ id: string }>();
  const { orgId } = useSession();
  const { mutate } = useSWRConfig();
  const path = `/api/v1/agents/${id}`;
  const { data: agent, error } = useOrgData<AgentDetail>(path);
  const { data: vocab } = usePolicy();
  const refresh = () => Promise.all([path, `${path}/config/versions`, `${path}/schedule`, `${path}/simulations`]
    .map((p) => mutate([p, orgId])));

  if (error) return <ErrorState error={error} />;
  if (!agent) return <Spinner />;
  const cfg = agent.current_config;
  return (
    <>
      <Link href="/app/agents" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-fg"><ArrowLeft className="size-4" /> Agent directory</Link>
      <PageHeader eyebrow={agent.definition.department} title={agent.name}
        description={agent.definition.title} actions={<LifecycleBadge status={agent.status} />} />
      <Actions agent={agent} onChange={refresh} />
      {cfg && <div className="mb-6 space-y-3"><IssueList issues={cfg.issues} /><GenerationNotes generation={cfg.generation} /></div>}
      {!cfg && agent.status !== "retired" && (
        <div className="mb-6">
          <EmptyState icon={Sparkles} title="No job description yet">
            Generate a proposed job description and task list from the catalog, your company profile, confirmed business rules and approved documents. You can edit everything before approval.
          </EmptyState>
        </div>
      )}
      <Tabs key={`${agent.id}-${cfg?.id ?? "none"}`} label="Agent profile" items={tabsFor(agent, cfg, refresh, vocab?.events)} />
    </>
  );
}
