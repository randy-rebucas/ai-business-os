"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ExecStatusBadge, RunStatusBadge } from "@/components/execution/shared";
import { Alert, Badge, ErrorState, Meta, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Figure, Figures, Notes, ReportSection } from "@/components/ui/report";
import { useOrgData } from "@/lib/hooks";
import type { DailyReportDetail, RunItem } from "@/lib/types";
import { formatDate, formatDateTime } from "@/lib/utils";

function Runs({ title, items }: { title: string; items: RunItem[] }) {
  return (
    <ReportSection title={`${title} (${items.length})`}>
      <ul className="divide-y divide-border">
        {items.map((r) => (
          <li key={r.run_id} className="py-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Link href={`/app/tasks/${r.run_id}`} className="font-semibold text-accent underline underline-offset-2">{r.task}</Link>
              <RunStatusBadge status={r.status} />
            </div>
            {(r.summary || r.reason) && <p className="mt-1 text-xs text-muted">{r.summary || r.reason}</p>}
          </li>
        ))}
      </ul>
    </ReportSection>
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
      <PageHeader context={`${c.agent.department} · ${c.agent.timezone}`} title={`${c.agent.name} — ${formatDate(r.report_date)}`}
        description={r.summary} actions={r.final ? <Badge tone="success">Final</Badge> : <Badge tone="info">So far (day not over)</Badge>} />
      <div className="space-y-6">
        <Alert tone="info" title="Built from records">Every line comes from this agent&apos;s task runs, its recorded tool calls and approvals — no AI model wrote this report. Links open the evidence.</Alert>
        <div className="grid items-start gap-8 xl:grid-cols-[1fr_16rem]">
          <Figures className="sm:grid-cols-2 lg:grid-cols-4">
            <Figure label="Actions completed" value={o.completed} note={1} detail={`of ${o.attempted} attempted`} />
            <Figure label="Outcome unknown" value={o.unverified} note={2} tone={o.unverified ? "danger" : undefined} />
            <Figure label="Failed" value={o.failed} tone={o.failed ? "danger" : undefined} />
            <Figure label="Not run" value={o.not_run} note={3} detail="refused, held, not connected or invalid" />
          </Figures>
          <Notes notes={[
            { key: 1, text: `Only actions that succeeded, or whose unknown outcome was later confirmed, count as completed. Evidence: ${c.evidence.runs} run${c.evidence.runs === 1 ? "" : "s"}, ${c.evidence.tool_executions} tool call${c.evidence.tool_executions === 1 ? "" : "s"}, ${c.evidence.action_requests} approval${c.evidence.action_requests === 1 ? "" : "s"}.`, href: "#actions", linkLabel: "Actions per tool" },
            { key: 2, text: "Sends whose result the provider never confirmed. They stay here until a reconciliation settles them — never counted as done." },
            { key: 3, text: "Attempts the platform stopped before they ran; each is listed per tool with its reason.", href: "#actions", linkLabel: "See them" },
          ]} />
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
        {(() => {
          const groups: { title: string; items: RunItem[] }[] = [
            { title: "Completed tasks", items: c.completed }, { title: "In progress", items: c.in_progress },
            { title: "Failed tasks", items: c.failed }, { title: "Blocked or skipped", items: c.blocked },
            { title: "Awaiting approval", items: awaitingRuns },
          ];
          const empty = groups.filter((g) => g.items.length === 0).map((g) => g.title.toLowerCase());
          return (
            <>
              {groups.filter((g) => g.items.length > 0).map((g) => <Runs key={g.title} title={g.title} items={g.items} />)}
              {approvals.length > 0 && (
                <ReportSection title={`Actions awaiting approval (${approvals.length})`}>
                  <ul className="divide-y divide-border">
                    {approvals.map((a) => <li key={a.request_id} className="py-3 text-sm">{a.action} <span className="block text-xs text-muted">{a.reason}</span> <Link href="/app/approvals" className="text-xs text-accent underline underline-offset-2">Decide</Link></li>)}
                  </ul>
                </ReportSection>
              )}
              {c.escalations.length > 0 && (
                <ReportSection title={`Escalations (${c.escalations.length})`}>
                  <ul className="divide-y divide-border">
                    {c.escalations.map((e) => <li key={e.execution_id} className="py-3 text-sm"><Badge tone={e.severity === "critical" ? "danger" : "warning"}>{e.severity}</Badge> <Link href={`/app/tasks/${e.run_id}`} className="text-accent underline underline-offset-2">{e.reason}</Link></li>)}
                  </ul>
                </ReportSection>
              )}
              {empty.length > 0 && (
                <p className="border-y border-border py-2.5 text-sm text-muted">
                  Nothing {empty.join(", ").replace(/, ([^,]*)$/, " or $1")}{c.escalations.length === 0 ? "; no escalations" : ""}{c.exceptions.length === 0 ? "; no exceptions or risks" : ""}.
                </p>
              )}
            </>
          );
        })()}
        <ReportSection id="actions" title="Actions performed" description="Per tool: attempts that ran, and how each ended. “Not run” = refused, held, not connected or invalid.">
          <Table label="Actions per tool">
            <thead><tr><th className={th}>Tool</th><th className={`${th} text-right`}>Attempted</th><th className={`${th} text-right`}>Succeeded</th><th className={`${th} text-right`}>Unknown</th><th className={`${th} text-right`}>Failed</th><th className={`${th} text-right`}>Not run</th></tr></thead>
            <tbody>
              {Object.entries(c.actions.per_tool).map(([tool, t]) => (
                <tr key={tool}><td className={td}><span className="ident text-xs">{tool}</span></td>{[t.attempted, t.succeeded, t.unverified, t.failed, t.not_run].map((v, i) => <td key={i} className={`${td} text-right`}>{v}</td>)}</tr>
              ))}
            </tbody>
          </Table>
          {c.actions.side_effects.length > 0 && (
            <ul className="divide-y divide-border">
              {c.actions.side_effects.map((x) => (
                <li key={x.execution_id} className="flex flex-wrap items-center gap-2 py-2.5 text-sm">
                  <ExecStatusBadge status={x.status} /> <span className="ident text-xs">{x.tool}</span>
                  <span className="text-xs text-muted">{x.evidence.map((e) => e.label).join(" · ")}</span>
                  <Link href={`/app/tasks/${x.run_id}`} className="text-xs text-accent underline underline-offset-2">evidence</Link>
                </li>
              ))}
            </ul>
          )}
        </ReportSection>
        <div className="grid gap-10 lg:grid-cols-2">
          {c.exceptions.length > 0 && (
            <ReportSection title="Exceptions and risks">
              <ul className="divide-y divide-border">
                {c.exceptions.map((e, i) => (
                  <li key={i} className="py-3 text-sm">
                    <Link href={`/app/tasks/${e.run_id}`} className="text-accent underline underline-offset-2">{e.task ?? e.tool}</Link> <span className="text-xs text-muted">({e.status})</span>
                    <p className="text-xs text-muted">{e.reason}{e.failed_checks?.length ? ` — ${e.failed_checks.join("; ")}` : ""}</p>
                  </li>
                ))}
              </ul>
            </ReportSection>
          )}
          <ReportSection title="Upcoming assignments">
            {c.upcoming.length === 0 ? <p className="py-2 text-sm text-muted">Nothing scheduled.</p> : (
              <ul className="divide-y divide-border">
                {c.upcoming.map((u, i) => <li key={i} className="flex justify-between gap-3 py-2.5 text-sm"><span>{u.task}{u.deferred && <span className="text-xs text-muted"> · deferred</span>}</span><span className="shrink-0 text-xs tabular-nums text-muted">{formatDateTime(u.at)}</span></li>)}
              </ul>
            )}
          </ReportSection>
          <ReportSection title="Performance against KPIs">
            <dl>
              {c.kpis.measured.map((k) => <Meta key={k.name} label={k.name}>{k.value} <span className="block text-xs text-muted">{k.basis}</span></Meta>)}
            </dl>
            <ul className="mt-2 border-t border-border pt-2 text-sm">
              {c.kpis.defined.map((k) => <li key={k.name} className="py-1">{k.name} (target {k.target}) — <span className="text-muted">{k.note}</span></li>)}
            </ul>
          </ReportSection>
          <ReportSection title="Costs and evidence">
            <dl>
              <Meta label="Model calls">{c.costs.model_calls}</Meta>
              <Meta label="Model cost">{c.costs.model_cost_usd} USD</Meta>
              <Meta label="Tool executions">{c.costs.tool_executions}</Meta>
              <Meta label="Evidence">{`${c.evidence.runs} run${c.evidence.runs === 1 ? "" : "s"} · ${c.evidence.tool_executions} calls · ${c.evidence.action_requests} approvals`}</Meta>
              <Meta label="Sources">{c.evidence.source_documents.join(", ") || "—"}</Meta>
              <Meta label="Assigned tasks">{c.assigned.map((t) => `${t.title} (${t.runs})`).join(" · ")}</Meta>
            </dl>
            {c.costs.label && <p className="mt-2 text-xs text-warning">{c.costs.label}</p>}
          </ReportSection>
        </div>
        <p className="text-xs text-muted">Version {r.version}, built {formatDateTime(r.generated_at)} · period {formatDateTime(r.period_start)} – {formatDateTime(r.period_end)}</p>
      </div>
    </>
  );
}
