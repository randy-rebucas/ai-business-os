"use client";

import Link from "next/link";
import { useState } from "react";

import { RunStatusBadge } from "@/components/execution/shared";
import { Badge, Capacity, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Input, Select } from "@/components/ui/form";
import { Figure, Figures, Notes, type ReportNote, ReportSection } from "@/components/ui/report";
import { useOrgData } from "@/lib/hooks";
import { LIFECYCLE, RUN_STATUS } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { CCItem, ControlCenter, UsageSummary } from "@/lib/types";
import { formatDate, formatDateTime } from "@/lib/utils";

/** Secondary counts, set as ruled lines of the statement rather than a wall of cards. */
function Ledger({ items }: { items: { label: string; value: number; tone?: "danger" | "warning" }[] }) {
  return (
    <dl className="mb-4 grid grid-cols-2 border-b border-border sm:grid-cols-4">
      {items.map((i) => (
        <div key={i.label} className="flex items-baseline justify-between gap-2 border-t border-border py-2 pr-4">
          <dt className="text-sm text-muted">{i.label}</dt>
          <dd className={`font-display text-lg font-bold ${i.value && i.tone === "danger" ? "text-danger" : i.value && i.tone === "warning" ? "text-warning" : "text-fg"}`}>{i.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function money(v: string | number, currency = "USD") {
  const n = Number(v).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${n} ${currency}` : n;
}

function plural(n: number, noun: string) {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

const num = "text-right tabular-nums";

function RunTable({ rows, label }: { rows: CCItem[]; label: string }) {
  if (!rows.length) return <p className="py-2 text-sm text-muted">None in this period.</p>;
  return (
    <>
      {/* Phones: one stacked ledger row per run. */}
      <ul aria-label={label} className="divide-y divide-border border-t-2 border-rule sm:hidden">
        {rows.map((r) => (
          <li key={r.run_id} className="space-y-1 py-2.5 text-sm">
            <div className="flex items-start justify-between gap-2">
              <Link href={`/app/tasks/${r.run_id}`} className="font-semibold text-accent underline">{r.task}</Link>
              <RunStatusBadge status={r.status} />
            </div>
            <p className="text-xs text-muted">{r.agent} · {r.priority} · {formatDateTime(r.created_at)}{r.overdue ? " · over SLA" : ""}</p>
          </li>
        ))}
      </ul>
      <div className="hidden sm:block">
        <Table label={label}>
          <thead><tr><th className={th}>Task</th><th className={th}>Agent</th><th className={th}>Priority</th><th className={th}>Status</th><th className={`${th} text-right`}>Created</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.run_id}>
                <td className={td}><Link href={`/app/tasks/${r.run_id}`} className="text-accent underline underline-offset-2">{r.task}</Link>
                  {r.overdue && <Badge tone="warning" className="ml-2">Over SLA</Badge>}</td>
                <td className={td}>{r.agent}</td>
                <td className={td}><span className="text-xs">{r.priority}</span></td>
                <td className={td}><RunStatusBadge status={r.status} /></td>
                <td className={`${td} ${num}`}><span className="text-xs">{formatDateTime(r.created_at)}</span></td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </>
  );
}

const filterLabel = "mb-1 block text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle";

export default function ControlCenterPage() {
  const [f, setF] = useState({ agent_id: "", department: "", status: "", priority: "", date_from: "", date_to: "" });
  const query = new URLSearchParams(Object.entries(f).filter(([, v]) => v));
  const { data, error } = useOrgData<ControlCenter>(`/api/v1/dashboard?${query}`, { refreshInterval: 15000, keepPreviousData: true });
  const { can } = useSession();
  const budget = useOrgData<UsageSummary>(can("usage.read") ? "/api/v1/usage" : null).data;
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });

  if (error) return <ErrorState error={error} />;
  if (!data) return <Spinner />;
  const t = data.tasks;
  const waiting = t.awaiting_approval + t.pending_actions;
  const broken = t.failed + t.unverified;
  const notes: ReportNote[] = [
    { key: 1, text: `Counted from ${plural(t.assigned, "run")} between ${formatDate(data.filters.date_from)} and ${formatDate(data.filters.date_to)}; a task counts as completed only when its run finished with every check passed.${broken ? "" : " No run failed and no outcome is unconfirmed."}`, href: "/app/tasks", linkLabel: "Open tasks & runs" },
    { key: 2, text: "Held actions wait for someone allowed to approve them; the runs behind them stay paused until then.", href: "/app/approvals", linkLabel: "Open the approval inbox" },
    { key: 3, text: `${data.costs.label}; the provider's invoice is authoritative.`, href: "/app/usage", linkLabel: "Open usage & costs" },
    ...(broken ? [{ key: 4, text: "An outcome nobody could confirm is never counted as done; each one is listed with its run.", href: "#attention", linkLabel: "See the list" }] : []),
  ];
  const attention = data.failed_workflows.length + data.overdue.length + data.escalations.length;

  return (
    <>
      <PageHeader title="Control Center"
        context={`${formatDate(data.filters.date_from)} – ${formatDate(data.filters.date_to)} · ${data.filters.timezone}`}
        description="Everything your AI employees did, counted from their execution records. Nothing here is estimated by a model." />
      <form className="mb-7 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3 lg:grid-cols-6" onSubmit={(e) => e.preventDefault()} aria-label="Filters">
        <label className="min-w-0"><span className={filterLabel}>Agent</span>
          <Select className="h-8 text-xs" value={f.agent_id} onChange={set("agent_id")}>
            <option value="">All agents</option>
            {data.options.agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </Select></label>
        <label className="min-w-0"><span className={filterLabel}>Department</span>
          <Select className="h-8 text-xs" value={f.department} onChange={set("department")}>
            <option value="">All</option>
            {data.options.departments.map((d) => <option key={d} value={d}>{d}</option>)}
          </Select></label>
        <label className="min-w-0"><span className={filterLabel}>Run status</span>
          <Select className="h-8 text-xs" value={f.status} onChange={set("status")}>
            <option value="">All</option>
            {Object.entries(RUN_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </Select></label>
        <label className="min-w-0"><span className={filterLabel}>Priority</span>
          <Select className="h-8 text-xs" value={f.priority} onChange={set("priority")}>
            <option value="">All</option>
            {["low", "normal", "high", "critical"].map((x) => <option key={x} value={x}>{x}</option>)}
          </Select></label>
        <label className="min-w-0"><span className={filterLabel}>From</span>
          <Input className="h-8 text-xs" type="date" value={f.date_from || data.filters.date_from} onChange={set("date_from")} /></label>
        <label className="min-w-0"><span className={filterLabel}>To</span>
          <Input className="h-8 text-xs" type="date" value={f.date_to || data.filters.date_to} onChange={set("date_to")} /></label>
      </form>

      <div className="space-y-10">
        <div className="grid items-start gap-8 xl:grid-cols-[1fr_16rem]">
          <Figures>
            <Figure label="Tasks completed" value={t.completed} note={1}
              detail={`of ${plural(t.assigned, "run")} · ${t.in_progress} in progress`} />
            <Figure label="Waiting for a decision" value={waiting} note={2} tone={waiting ? "warning" : undefined}
              detail={`${plural(t.pending_actions, "held action")} · ${plural(t.awaiting_approval, "run")} paused`} />
            <Figure label="AI cost in period" value={money(data.costs.total_usd, "")} unit="USD" note={3} size="md">
              {budget?.company_budget?.comparable && (
                <Capacity used={Number(budget.month_to_date_usd)} limit={Number(budget.company_budget.amount)}
                  label="Month-to-date spend against the company budget" format={(n) => money(n)} />
              )}
            </Figure>
            {broken > 0 && (
              <Figure label="Failed or unconfirmed" value={broken} note={4} tone="danger"
                detail={`${t.failed} failed · ${t.unverified} outcome unknown`} />
            )}
          </Figures>
          <Notes notes={notes} />
        </div>

        <ReportSection title="Recent activity">
          <RunTable rows={data.recent} label="Recent runs" />
        </ReportSection>

        {data.needs_retest.length > 0 && (
          <ReportSection title="Needs re-testing" description="Something material changed since these agents last passed their readiness tests. They can't be resumed or widened until they pass again.">
            <ul className="divide-y divide-border">
              {data.needs_retest.map((a) => (
                <li key={a.instance_id} className="py-3 text-sm">
                  <Link href={`/app/agents/${a.instance_id}/readiness`} className="font-semibold text-accent underline underline-offset-2">{a.agent}</Link>{" "}
                  <span className="text-muted">({a.status})</span>
                  <ul className="mt-1 list-disc pl-5 text-muted">{a.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                </li>
              ))}
            </ul>
          </ReportSection>
        )}

        <div id="attention" className="scroll-mt-24 space-y-10">
          {attention === 0 ? (
            <p className="border-y-2 border-rule py-3 text-sm text-muted">
              No failed, unverified, over-SLA or escalated work in this period.
            </p>
          ) : (
            <>
              {data.failed_workflows.length > 0 && (
                <ReportSection title="Failed and unverified workflows"><RunTable rows={data.failed_workflows} label="Failed workflows" /></ReportSection>
              )}
              {data.overdue.length > 0 && (
                <ReportSection title="Over their SLA"><RunTable rows={data.overdue} label="Runs over SLA" /></ReportSection>
              )}
              {data.escalations.length > 0 && (
                <ReportSection title="Important escalations" description="High and critical escalations raised by agents.">
                  <ul className="divide-y divide-border">
                    {data.escalations.map((e) => (
                      <li key={e.execution_id} className="py-3 text-sm">
                        <Badge tone={e.severity === "critical" ? "danger" : "warning"}>{e.severity}</Badge>{" "}
                        <Link href={`/app/tasks/${e.run_id}`} className="text-accent underline underline-offset-2">{e.agent}</Link>
                        <p className="mt-1 text-muted">{e.reason}</p>
                      </li>
                    ))}
                  </ul>
                </ReportSection>
              )}
            </>
          )}
        </div>

        <ReportSection title="Agent performance" description="Completion rate = runs completed with every check passed ÷ runs finished.">
          <Ledger items={[
            { label: "AI employees", value: data.agents.total }, { label: "Active", value: data.agents.active },
            { label: "Paused", value: data.agents.paused }, { label: "Failed agents", value: data.agents.failed, tone: "danger" },
            { label: "Over SLA", value: t.overdue, tone: "warning" },
            { label: "Needs review", value: t.needs_review, tone: "warning" },
            { label: "Blocked or skipped", value: t.blocked, tone: "warning" },
            { label: "Runs in period", value: t.assigned },
          ]} />
          {data.performance.length === 0 ? <p className="py-2 text-sm text-muted">No agents match.</p> : (
            <>
              <ul aria-label="Agent performance" className="divide-y divide-border border-t-2 border-rule sm:hidden">
                {data.performance.map((p) => (
                  <li key={p.instance_id} className="space-y-1 py-2.5 text-sm">
                    <div className="flex items-start justify-between gap-2">
                      <Link href={`/app/agents/${p.instance_id}`} className="font-semibold text-accent underline">{p.agent}</Link>
                      <Badge tone={LIFECYCLE[p.status].tone}>{LIFECYCLE[p.status].label}</Badge>
                    </div>
                    <p className="text-xs text-muted">
                      {p.completed} of {plural(p.runs, "run")} completed{p.completion_rate == null ? "" : ` (${Math.round(p.completion_rate * 100)}%)`} · {p.failed} failed · {p.unverified} unknown · {p.cost_usd} USD
                    </p>
                  </li>
                ))}
              </ul>
              <div className="hidden sm:block">
                <Table label="Agent performance">
                  <thead><tr><th className={th}>Agent</th><th className={th}>Status</th><th className={`${th} text-right`}>Runs</th><th className={`${th} text-right`}>Completed</th><th className={`${th} text-right`}>Rate</th><th className={`${th} text-right`}>Failed / unknown</th><th className={`${th} text-right`}>Avg time</th><th className={`${th} text-right`}>Cost (USD)</th></tr></thead>
                  <tbody>
                    {data.performance.map((p) => (
                      <tr key={p.instance_id}>
                        <td className={td}><Link href={`/app/agents/${p.instance_id}`} className="text-accent underline underline-offset-2">{p.agent}</Link><div className="text-xs text-muted">{p.department}</div></td>
                        <td className={td}><Badge tone={LIFECYCLE[p.status].tone}>{LIFECYCLE[p.status].label}</Badge></td>
                        <td className={`${td} ${num}`}>{p.runs}</td><td className={`${td} ${num}`}>{p.completed}</td>
                        <td className={`${td} ${num}`}>{p.completion_rate == null ? "—" : `${Math.round(p.completion_rate * 100)}%`}</td>
                        <td className={`${td} ${num}`}>{p.failed} / {p.unverified}</td>
                        <td className={`${td} ${num}`}>{p.avg_duration_seconds == null ? "—" : `${p.avg_duration_seconds}s`}</td>
                        <td className={`${td} ${num}`}>{p.cost_usd}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            </>
          )}
        </ReportSection>

        <ReportSection title="Upcoming work" description="Next scheduled runs of active agents, and runs waiting for business hours.">
          {data.upcoming.length === 0 ? <p className="py-2 text-sm text-muted">Nothing scheduled.</p> : (
            <ul className="divide-y divide-border">
              {data.upcoming.map((u, i) => (
                <li key={`${u.instance_id}-${u.task}-${i}`} className="flex justify-between gap-3 py-2.5 text-sm">
                  <span>{u.task} <span className="block text-xs text-muted">{u.agent}{u.deferred ? " · deferred to business hours" : ""}</span></span>
                  <span className="shrink-0 text-xs tabular-nums text-muted">{formatDateTime(u.at)}</span>
                </li>
              ))}
            </ul>
          )}
        </ReportSection>
      </div>
    </>
  );
}
