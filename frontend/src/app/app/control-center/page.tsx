"use client";

import Link from "next/link";
import { useState } from "react";

import { RunStatusBadge } from "@/components/execution/shared";
import { Badge, Card, CardHeader, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Field, Input, Select } from "@/components/ui/form";
import { useOrgData } from "@/lib/hooks";
import { LIFECYCLE, RUN_STATUS } from "@/lib/labels";
import type { CCItem, ControlCenter } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

function Stat({ label, value, tone, href }: { label: string; value: number | string; tone?: "danger" | "warning"; href?: string }) {
  const body = (
    <Card className="px-4 py-3">
      <p className="text-xs text-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone === "danger" && value ? "text-danger" : tone === "warning" && value ? "text-warning" : "text-fg"}`}>{value}</p>
    </Card>
  );
  return href ? <Link href={href} className="block rounded-lg focus-visible:outline-2 focus-visible:outline-accent">{body}</Link> : body;
}

function RunTable({ rows, label }: { rows: CCItem[]; label: string }) {
  if (!rows.length) return <p className="px-5 py-4 text-sm text-muted">None.</p>;
  return (
    <Table label={label}>
      <thead><tr><th className={th}>Task</th><th className={th}>Agent</th><th className={th}>Priority</th><th className={th}>Status</th><th className={th}>Created</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.run_id}>
            <td className={td}><Link href={`/app/tasks/${r.run_id}`} className="text-accent underline underline-offset-2">{r.task}</Link>
              {r.overdue && <Badge tone="warning" className="ml-2">Over SLA</Badge>}</td>
            <td className={td}>{r.agent}</td>
            <td className={td}><span className="text-xs">{r.priority}</span></td>
            <td className={td}><RunStatusBadge status={r.status} /></td>
            <td className={td}><span className="text-xs">{formatDateTime(r.created_at)}</span></td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export default function ControlCenterPage() {
  const [f, setF] = useState({ agent_id: "", department: "", status: "", priority: "", date_from: "", date_to: "" });
  const query = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
  const { data, error } = useOrgData<ControlCenter>(`/api/v1/dashboard?${query}`, { refreshInterval: 15000, keepPreviousData: true });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <>
      <PageHeader eyebrow="AI workforce" title="Control Center"
        description="Everything your AI employees did, counted from their execution records. Nothing here is estimated by a model." />
      {error ? <ErrorState error={error} /> : !data ? <Spinner /> : (
        <div className="space-y-6">
          <Card className="px-5 py-4">
            <form className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6" onSubmit={(e) => e.preventDefault()} aria-label="Filters">
              <Field label="Agent">{(p) => (
                <Select {...p} value={f.agent_id} onChange={set("agent_id")}>
                  <option value="">All agents</option>
                  {data.options.agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </Select>)}</Field>
              <Field label="Department">{(p) => (
                <Select {...p} value={f.department} onChange={set("department")}>
                  <option value="">All</option>
                  {data.options.departments.map((d) => <option key={d} value={d}>{d}</option>)}
                </Select>)}</Field>
              <Field label="Run status">{(p) => (
                <Select {...p} value={f.status} onChange={set("status")}>
                  <option value="">All</option>
                  {Object.entries(RUN_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </Select>)}</Field>
              <Field label="Priority">{(p) => (
                <Select {...p} value={f.priority} onChange={set("priority")}>
                  <option value="">All</option>
                  {["low", "normal", "high", "critical"].map((x) => <option key={x} value={x}>{x}</option>)}
                </Select>)}</Field>
              <Field label="From">{(p) => <Input {...p} type="date" value={f.date_from || data.filters.date_from} onChange={set("date_from")} />}</Field>
              <Field label="To">{(p) => <Input {...p} type="date" value={f.date_to || data.filters.date_to} onChange={set("date_to")} />}</Field>
            </form>
            <p className="mt-2 text-xs text-muted">Days in {data.filters.timezone}.</p>
          </Card>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            <Stat label="AI employees" value={data.agents.total} />
            <Stat label="Active" value={data.agents.active} />
            <Stat label="Paused" value={data.agents.paused} />
            <Stat label="Failed agents" value={data.agents.failed} tone="danger" />
            <Stat label="Tasks run" value={data.tasks.assigned} href="/app/tasks" />
            <Stat label="Completed" value={data.tasks.completed} />
            <Stat label="Awaiting approval" value={data.tasks.awaiting_approval + data.tasks.pending_actions} tone="warning" href="/app/approvals" />
            <Stat label="Over SLA" value={data.tasks.overdue} tone="warning" />
            <Stat label="Failed workflows" value={data.tasks.failed} tone="danger" />
            <Stat label="Outcome unknown" value={data.tasks.unverified} tone="danger" />
            <Stat label="Needs review" value={data.tasks.needs_review} tone="warning" />
            <Stat label="AI cost (USD)" value={data.costs.total_usd} href="/app/usage" />
          </div>
          <Card>
            <CardHeader title="Agent performance" description="Completion rate = runs completed with every check passed ÷ runs finished." />
            {data.performance.length === 0 ? <p className="px-5 py-4 text-sm text-muted">No agents match.</p> : (
              <Table label="Agent performance">
                <thead><tr><th className={th}>Agent</th><th className={th}>Status</th><th className={th}>Runs</th><th className={th}>Completed</th><th className={th}>Rate</th><th className={th}>Failed / unknown</th><th className={th}>Avg time</th><th className={th}>Cost</th></tr></thead>
                <tbody>
                  {data.performance.map((p) => (
                    <tr key={p.instance_id}>
                      <td className={td}><Link href={`/app/agents/${p.instance_id}`} className="text-accent underline underline-offset-2">{p.agent}</Link><div className="text-xs text-muted">{p.department}</div></td>
                      <td className={td}><Badge tone={LIFECYCLE[p.status].tone}>{LIFECYCLE[p.status].label}</Badge></td>
                      <td className={td}>{p.runs}</td><td className={td}>{p.completed}</td>
                      <td className={td}>{p.completion_rate == null ? "—" : `${Math.round(p.completion_rate * 100)}%`}</td>
                      <td className={td}>{p.failed} / {p.unverified}</td>
                      <td className={td}>{p.avg_duration_seconds == null ? "—" : `${p.avg_duration_seconds}s`}</td>
                      <td className={td}>{p.cost_usd} USD</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
            <p className="px-5 py-2 text-xs text-muted">{data.costs.label}</p>
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            {data.needs_retest.length > 0 && (
              <Card className="lg:col-span-2">
                <CardHeader title="Needs re-testing" description="Something material changed since these agents last passed their readiness tests. They can't be resumed or widened until they pass again." />
                <ul className="divide-y divide-border">
                  {data.needs_retest.map((a) => (
                    <li key={a.instance_id} className="px-5 py-3 text-sm">
                      <Link href={`/app/agents/${a.instance_id}/readiness`} className="font-medium text-accent underline underline-offset-2">{a.agent}</Link>{" "}
                      <span className="text-muted">({a.status})</span>
                      <ul className="mt-1 list-disc pl-5 text-muted">{a.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
            <Card><CardHeader title="Failed and unverified workflows" /><RunTable rows={data.failed_workflows} label="Failed workflows" /></Card>
            <Card><CardHeader title="Over their SLA" /><RunTable rows={data.overdue} label="Runs over SLA" /></Card>
            <Card>
              <CardHeader title="Important escalations" description="High and critical escalations raised by agents." />
              {data.escalations.length === 0 ? <p className="px-5 py-4 text-sm text-muted">None.</p> : (
                <ul className="divide-y divide-border">
                  {data.escalations.map((e) => (
                    <li key={e.execution_id} className="px-5 py-3 text-sm">
                      <Badge tone={e.severity === "critical" ? "danger" : "warning"}>{e.severity}</Badge>{" "}
                      <Link href={`/app/tasks/${e.run_id}`} className="text-accent underline underline-offset-2">{e.agent}</Link>
                      <p className="mt-1 text-muted">{e.reason}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <CardHeader title="Upcoming work" description="Next scheduled runs of active agents, and runs waiting for business hours." />
              {data.upcoming.length === 0 ? <p className="px-5 py-4 text-sm text-muted">Nothing scheduled.</p> : (
                <ul className="divide-y divide-border">
                  {data.upcoming.map((u, i) => (
                    <li key={`${u.instance_id}-${u.task}-${i}`} className="flex justify-between gap-3 px-5 py-2.5 text-sm">
                      <span>{u.task} <span className="block text-xs text-muted">{u.agent}{u.deferred ? " · deferred to business hours" : ""}</span></span>
                      <span className="text-xs text-muted">{formatDateTime(u.at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
          <Card><CardHeader title="Recent activity" /><RunTable rows={data.recent} label="Recent runs" /></Card>
        </div>
      )}
    </>
  );
}
