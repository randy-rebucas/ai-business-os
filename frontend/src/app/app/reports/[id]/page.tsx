"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ExecStatusBadge, RunStatusBadge } from "@/components/execution/shared";
import { Alert, Badge, Card, CardHeader, ErrorState, Meta, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { useOrgData } from "@/lib/hooks";
import type { DailyReportDetail, RunItem } from "@/lib/types";
import { formatDate, formatDateTime } from "@/lib/utils";

function Runs({ title, items, empty }: { title: string; items: RunItem[]; empty: string }) {
  return (
    <Card>
      <CardHeader title={`${title} (${items.length})`} />
      {items.length === 0 ? <p className="px-5 py-3 text-sm text-muted">{empty}</p> : (
        <ul className="divide-y divide-border">
          {items.map((r) => (
            <li key={r.run_id} className="px-5 py-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Link href={`/app/tasks/${r.run_id}`} className="font-medium text-accent underline underline-offset-2">{r.task}</Link>
                <RunStatusBadge status={r.status} />
              </div>
              {(r.summary || r.reason) && <p className="mt-1 text-xs text-muted">{r.summary || r.reason}</p>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const { data: r, error } = useOrgData<DailyReportDetail>(`/api/v1/reports/${id}`);
  if (error) return <ErrorState error={error} />;
  if (!r) return <Spinner />;
  const c = r.content;
  const o = c.outcomes;
  const approvals = c.awaiting_approval.filter((x) => "request_id" in x) as { request_id: string; run_id: string; action: string; reason: string }[];
  const awaitingRuns = c.awaiting_approval.filter((x) => !("request_id" in x)) as RunItem[];
  return (
    <>
      <Link href="/app/reports" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-fg"><ArrowLeft className="size-4" /> Daily reports</Link>
      <PageHeader eyebrow={`${c.agent.department} · ${c.agent.timezone}`} title={`${c.agent.name} — ${formatDate(r.report_date)}`}
        description={r.summary} actions={r.final ? <Badge tone="success">Final</Badge> : <Badge tone="info">So far (day not over)</Badge>} />
      <div className="space-y-6">
        <Alert tone="info" title="Built from records">Every line comes from this agent&apos;s task runs, its recorded tool calls and approvals — no AI model wrote this report. Links open the evidence.</Alert>
        <div className="grid gap-3 sm:grid-cols-5">
          {([["Attempted", o.attempted], ["Completed", o.completed], ["Outcome unknown", o.unverified], ["Failed", o.failed], ["Not run", o.not_run]] as const).map(([k, v]) => (
            <Card key={k} className="px-4 py-3"><p className="text-xs text-muted">{k} actions</p><p className="mt-1 text-2xl font-semibold">{v}</p></Card>
          ))}
        </div>
        {o.unverified_items.length > 0 && (
          <Alert tone="danger" title="Outcome unknown — not counted as done">
            <ul className="list-disc pl-4">{o.unverified_items.map((u) => <li key={u.execution_id}><Link href={`/app/tasks/${u.run_id}`} className="underline">{u.tool}</Link>: {u.reason}</li>)}</ul>
          </Alert>
        )}
        {o.reconciled.length > 0 && (
          <Alert tone="success" title="Settled after the fact">
            <ul className="list-disc pl-4">{o.reconciled.map((u) => <li key={u.execution_id}>{u.tool}: {u.outcome} — {u.detail}</li>)}</ul>
          </Alert>
        )}
        <div className="grid gap-6 lg:grid-cols-2">
          <Runs title="Completed tasks" items={c.completed} empty="None." />
          <Runs title="In progress" items={c.in_progress} empty="None." />
          <Runs title="Failed tasks" items={c.failed} empty="None." />
          <Runs title="Blocked or skipped" items={c.blocked} empty="None." />
          <Card>
            <CardHeader title={`Awaiting approval (${awaitingRuns.length + approvals.length})`} />
            {awaitingRuns.length + approvals.length === 0 ? <p className="px-5 py-3 text-sm text-muted">None.</p> : (
              <ul className="divide-y divide-border">
                {awaitingRuns.map((x) => <li key={x.run_id} className="px-5 py-3 text-sm"><Link href={`/app/tasks/${x.run_id}`} className="text-accent underline underline-offset-2">{x.task}</Link></li>)}
                {approvals.map((a) => <li key={a.request_id} className="px-5 py-3 text-sm">{a.action} <span className="block text-xs text-muted">{a.reason}</span> <Link href="/app/approvals" className="text-xs text-accent underline underline-offset-2">Decide</Link></li>)}
              </ul>
            )}
          </Card>
          <Card>
            <CardHeader title={`Escalations (${c.escalations.length})`} />
            {c.escalations.length === 0 ? <p className="px-5 py-3 text-sm text-muted">None.</p> : (
              <ul className="divide-y divide-border">
                {c.escalations.map((e) => <li key={e.execution_id} className="px-5 py-3 text-sm"><Badge tone={e.severity === "critical" ? "danger" : "warning"}>{e.severity}</Badge> <Link href={`/app/tasks/${e.run_id}`} className="text-accent underline underline-offset-2">{e.reason}</Link></li>)}
              </ul>
            )}
          </Card>
        </div>
        <Card>
          <CardHeader title="Actions performed" description="Per tool: attempts that ran, and how each ended. “Not run” = refused, held, not connected or invalid." />
          <Table label="Actions per tool">
            <thead><tr><th className={th}>Tool</th><th className={th}>Attempted</th><th className={th}>Succeeded</th><th className={th}>Unknown</th><th className={th}>Failed</th><th className={th}>Not run</th></tr></thead>
            <tbody>
              {Object.entries(c.actions.per_tool).map(([tool, t]) => (
                <tr key={tool}><td className={td}><span className="ident text-xs">{tool}</span></td><td className={td}>{t.attempted}</td><td className={td}>{t.succeeded}</td><td className={td}>{t.unverified}</td><td className={td}>{t.failed}</td><td className={td}>{t.not_run}</td></tr>
              ))}
            </tbody>
          </Table>
          {c.actions.side_effects.length > 0 && (
            <ul className="divide-y divide-border border-t border-border">
              {c.actions.side_effects.map((x) => (
                <li key={x.execution_id} className="flex flex-wrap items-center gap-2 px-5 py-2.5 text-sm">
                  <ExecStatusBadge status={x.status} /> <span className="ident text-xs">{x.tool}</span>
                  <span className="text-xs text-muted">{x.evidence.map((e) => e.label).join(" · ")}</span>
                  <Link href={`/app/tasks/${x.run_id}`} className="text-xs text-accent underline underline-offset-2">evidence</Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Exceptions and risks" />
            {c.exceptions.length === 0 ? <p className="px-5 py-3 text-sm text-muted">None.</p> : (
              <ul className="divide-y divide-border">
                {c.exceptions.map((e, i) => (
                  <li key={i} className="px-5 py-3 text-sm">
                    <Link href={`/app/tasks/${e.run_id}`} className="text-accent underline underline-offset-2">{e.task ?? e.tool}</Link> <span className="text-xs text-muted">({e.status})</span>
                    <p className="text-xs text-muted">{e.reason}{e.failed_checks?.length ? ` — ${e.failed_checks.join("; ")}` : ""}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <CardHeader title="Upcoming assignments" />
            {c.upcoming.length === 0 ? <p className="px-5 py-3 text-sm text-muted">Nothing scheduled.</p> : (
              <ul className="divide-y divide-border">
                {c.upcoming.map((u, i) => <li key={i} className="flex justify-between px-5 py-2.5 text-sm"><span>{u.task}{u.deferred && <span className="text-xs text-muted"> · deferred</span>}</span><span className="text-xs text-muted">{formatDateTime(u.at)}</span></li>)}
              </ul>
            )}
          </Card>
          <Card>
            <CardHeader title="Performance against KPIs" />
            <dl className="px-5 py-3">
              {c.kpis.measured.map((k) => <Meta key={k.name} label={k.name}>{k.value} <span className="block text-xs text-muted">{k.basis}</span></Meta>)}
            </dl>
            <ul className="border-t border-border px-5 py-3 text-sm">
              {c.kpis.defined.map((k) => <li key={k.name} className="py-1">{k.name} (target {k.target}) — <span className="text-muted">{k.note}</span></li>)}
            </ul>
          </Card>
          <Card>
            <CardHeader title="Costs and evidence" />
            <dl className="px-5 py-3">
              <Meta label="Model calls">{c.costs.model_calls}</Meta>
              <Meta label="Model cost">{c.costs.model_cost_usd} USD</Meta>
              <Meta label="Tool executions">{c.costs.tool_executions}</Meta>
              <Meta label="Evidence">{`${c.evidence.runs} runs · ${c.evidence.tool_executions} calls · ${c.evidence.action_requests} approvals`}</Meta>
              <Meta label="Sources">{c.evidence.source_documents.join(", ") || "—"}</Meta>
              <Meta label="Assigned tasks">{c.assigned.map((t) => `${t.title} (${t.runs})`).join(" · ")}</Meta>
            </dl>
            {c.costs.label && <p className="px-5 pb-3 text-xs text-warning">{c.costs.label}</p>}
          </Card>
        </div>
        <p className="text-xs text-muted">Version {r.version}, built {formatDateTime(r.generated_at)} · period {formatDateTime(r.period_start)} – {formatDateTime(r.period_end)}</p>
      </div>
    </>
  );
}
