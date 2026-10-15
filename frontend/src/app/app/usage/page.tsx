"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Capacity, Card, CardHeader, ErrorState, Meta, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/form";
import { useOrgData } from "@/lib/hooks";
import type { UsageSummary } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export default function UsagePage() {
  const [range, setRange] = useState({ date_from: "", date_to: "" });
  const query = new URLSearchParams(Object.entries(range).filter(([, v]) => v));
  const { data: u, error } = useOrgData<UsageSummary>(`/api/v1/usage?${query}`, { keepPreviousData: true });
  return (
    <>
      <PageHeader title="Usage & costs"
        description="Every AI model call and tool execution, from the usage ledger. Agents stop running when they reach their approved monthly budget." />
      {error ? <ErrorState error={error} /> : !u ? <Spinner /> : (
        <div className="space-y-6">
          <Card className="flex flex-wrap items-end gap-3 px-5 py-4">
            <Field label="From" className="w-44">{(p) => <Input {...p} type="date" value={range.date_from || u.from} onChange={(e) => setRange({ ...range, date_from: e.target.value })} />}</Field>
            <Field label="To" className="w-44">{(p) => <Input {...p} type="date" value={range.date_to || u.to} onChange={(e) => setRange({ ...range, date_to: e.target.value })} />}</Field>
            <p className="text-xs text-muted">Days in {u.timezone}.</p>
          </Card>
          {u.dev_label && <Alert tone="warning" title="Development mode">{u.dev_label} ({u.dev_calls} of {u.calls} calls).</Alert>}
          <div className="grid gap-3 sm:grid-cols-5">
            {([["Model cost (USD)", u.total_cost_usd], ["Model calls", u.calls], ["Errors / refusals", u.errors], ["Task runs", u.runs], ["Tool executions", u.tool_executions]] as const).map(([k, v]) => (
              <Card key={k} className="px-4 py-3"><p className="text-xs text-muted">{k}</p><p className="mt-1 text-2xl font-semibold">{v}</p></Card>
            ))}
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Budgets this month" description={`Spent so far: ${u.month_to_date_usd} USD`} />
              {u.company_budget && (
                <div className="border-b border-border px-5 py-3">
                  <dl>
                    <Meta label="Company budget">{`${u.company_budget.amount} ${u.company_budget.currency}`}{!u.company_budget.comparable && <span className="block text-xs text-muted">Not in USD — no exchange rate is assumed, so it isn&apos;t compared.</span>}
                      {u.company_budget.over && <Badge tone="danger" className="ml-2">Reached</Badge>}</Meta>
                  </dl>
                  {u.company_budget.comparable && (
                    <div className="mt-2"><Capacity used={Number(u.month_to_date_usd)} limit={Number(u.company_budget.amount)}
                      label="Month-to-date spend against the company budget" format={(n) => `${n.toFixed(2)} USD`} /></div>
                  )}
                </div>
              )}
              <Table label="Agent budgets">
                <thead><tr><th className={th}>Agent</th><th className={th}>Budget</th><th className={th}>Spent</th><th className={th}>Remaining</th></tr></thead>
                <tbody>
                  {u.agent_budgets.map((b) => (
                    <tr key={b.instance_id}>
                      <td className={td}><Link href={`/app/agents/${b.instance_id}`} className="text-accent underline underline-offset-2">{b.agent}</Link></td>
                      <td className={td}>{b.budget_usd ?? "—"}</td>
                      <td className={`${td} min-w-40`}>{b.budget_usd != null
                        ? <Capacity used={Number(b.spent_usd)} limit={Number(b.budget_usd)} label={`${b.agent} spend against its monthly budget`} format={(n) => `${n.toFixed(2)} USD`} />
                        : b.spent_usd}</td>
                      <td className={td}>{b.over ? <Badge tone="danger">Reached — runs skipped</Badge> : b.remaining_usd ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>
            <Card>
              <CardHeader title="By agent" />
              <Table label="Usage by agent">
                <thead><tr><th className={th}>Agent</th><th className={th}>Calls</th><th className={th}>Tokens in / out</th><th className={th}>Cost (USD)</th></tr></thead>
                <tbody>
                  {u.by_agent.map((a) => (
                    <tr key={a.instance_id ?? "none"}><td className={td}>{a.agent}</td><td className={td}>{a.calls}</td><td className={td}>{a.input_tokens} / {a.output_tokens}</td><td className={td}>{a.cost_usd}</td></tr>
                  ))}
                </tbody>
              </Table>
            </Card>
            <Card>
              <CardHeader title="By purpose" />
              <Table label="Usage by purpose">
                <thead><tr><th className={th}>Purpose</th><th className={th}>Calls</th><th className={th}>Cost (USD)</th></tr></thead>
                <tbody>{u.by_purpose.map((p) => <tr key={p.purpose}><td className={td}><span className="ident text-xs">{p.purpose}</span></td><td className={td}>{p.calls}</td><td className={td}>{p.cost_usd}</td></tr>)}</tbody>
              </Table>
            </Card>
            <Card>
              <CardHeader title="By day" />
              <Table label="Usage by day">
                <thead><tr><th className={th}>Day</th><th className={th}>Calls</th><th className={th}>Cost (USD)</th></tr></thead>
                <tbody>{u.daily.map((d) => <tr key={d.date}><td className={td}>{formatDate(d.date)}</td><td className={td}>{d.calls}</td><td className={td}>{d.cost_usd}</td></tr>)}</tbody>
              </Table>
            </Card>
          </div>
          <p className="text-xs text-muted">{u.note}</p>
        </div>
      )}
    </>
  );
}
