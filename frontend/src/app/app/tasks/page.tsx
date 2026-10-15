"use client";

import { ListChecks, Play, Send } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { isActive, RunStatusBadge } from "@/components/execution/shared";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Field, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { pollWhile, useOrgData } from "@/lib/hooks";
import { RUN_STATUS, TRIGGER_LABEL } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { RunnableAgent, WorkflowRun } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

function trigger(t: RunnableAgent["tasks"][number]): string {
  if (t.trigger_type === "event") return `On event ${t.event}`;
  if (t.trigger_type === "schedule" && t.schedule) {
    return t.schedule.kind === "weekly" ? `${t.schedule.days.join(", ")} at ${t.schedule.time}` : `Monthly on day ${t.schedule.day} at ${t.schedule.time}`;
  }
  return "On demand";
}

export default function TasksPage() {
  const router = useRouter();
  const { can } = useSession();
  const [status, setStatus] = useState("");
  const [agentId, setAgentId] = useState("");
  const [request, setRequest] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const agents = useOrgData<RunnableAgent[]>("/api/v1/workflows/tasks");
  const query = new URLSearchParams({ top_level: "true", limit: "100", ...(status ? { status } : {}) });
  const runs = useOrgData<WorkflowRun[]>(`/api/v1/workflows?${query}`, pollWhile<WorkflowRun[]>((rs) => rs.some(isActive), 2000));
  const runnable = (agents.data ?? []).filter((a) => a.can_run);
  const manage = can("task.manage");

  const start = async (key: string, body: Record<string, unknown>) => {
    setBusy(key);
    setError(null);
    try {
      const run = await api<{ id: string }>("/api/v1/workflows", { method: "POST", org: true, body });
      router.push(`/app/tasks/${run.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader title="Tasks"
        description="Run an active agent's approved tasks now, or ask an agent something. Every step is checked against its approved permissions and recorded as evidence. Scheduled and event-driven tasks start on their own." />
      {error && <Alert tone="danger" className="mb-6">{error}</Alert>}
      {agents.error ? <ErrorState error={agents.error} /> : !agents.data ? <Spinner /> : (
        <div className="mb-10 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <Card>
            <CardHeader title="Approved tasks" description="Only active agents can run. In observation mode they read and draft; anything else waits for your approval." />
            {agents.data.length === 0 ? <p className="px-5 py-4 text-sm text-muted">No agents hired yet. <Link href="/app/agents/team" className="text-accent underline underline-offset-2">Build your team</Link>.</p> : (
              <ul className="divide-y divide-border">
                {agents.data.map((a) => (
                  <li key={a.instance_id} className="px-5 py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link href={`/app/agents/${a.instance_id}`} className="font-medium text-fg underline-offset-2 hover:underline">{a.agent_name}</Link>
                      {a.can_run ? <Badge tone={a.deployment_stage === "full" ? "success" : "info"}>{a.deployment_stage === "full" ? "Full permissions" : "Observation mode"}</Badge>
                        : <span className="text-xs text-muted">{a.reason}</span>}
                    </div>
                    {a.can_run && (
                      <ul className="mt-2 space-y-2">
                        {a.tasks.map((t) => (
                          <li key={t.key} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                            <span>{t.title} <span className="block text-xs text-muted">{trigger(t)}</span></span>
                            {manage && <Button size="sm" variant="secondary" loading={busy === `${a.instance_id}:${t.key}`} disabled={!!busy}
                              onClick={() => start(`${a.instance_id}:${t.key}`, { agent_id: a.instance_id, task_key: t.key })}><Play /> Run now</Button>}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card className="self-start">
            <CardHeader title="Ask an agent" description="The Executive agent asks the other active agents and consolidates their verified results." />
            {!manage ? <p className="px-5 py-4 text-sm text-muted">Managers and above can start tasks.</p> : runnable.length === 0 ? (
              <p className="px-5 py-4 text-sm text-muted">No active agent yet. Activate one from its readiness page.</p>
            ) : (
              <form className="space-y-3 px-5 py-4" onSubmit={(e) => { e.preventDefault(); start("request", { agent_id: agentId || runnable[0].instance_id, request }); }}>
                <Field label="Agent">{(p) => (
                  <Select {...p} value={agentId || runnable[0].instance_id} onChange={(e) => setAgentId(e.target.value)}>
                    {runnable.map((a) => <option key={a.instance_id} value={a.instance_id}>{a.agent_name}</option>)}
                  </Select>
                )}</Field>
                <Field label="Request">{(p) => <Textarea {...p} value={request} maxLength={2000} required onChange={(e) => setRequest(e.target.value)} placeholder="e.g. Which receivables need attention this week?" />}</Field>
                <Button type="submit" loading={busy === "request"} disabled={!!busy || !request.trim()}><Send /> Send request</Button>
              </form>
            )}
          </Card>
        </div>
      )}
      <section aria-labelledby="runs-h">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <h2 id="runs-h" className="text-sm font-semibold">Runs</h2>
          <Field label="Status" className="w-48">{(p) => (
            <Select {...p} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              {Object.entries(RUN_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </Select>
          )}</Field>
        </div>
        {runs.error ? <ErrorState error={runs.error} /> : !runs.data ? <Spinner /> : runs.data.length === 0 ? (
          <EmptyState icon={ListChecks} title="No runs yet">Runs appear here when a task starts — on demand, on schedule or after a business event.</EmptyState>
        ) : (
          <Table label="Task runs">
            <thead><tr><th className={th}>Task</th><th className={th}>Agent</th><th className={th}>Trigger</th><th className={th}>Status</th><th className={th}>Started</th></tr></thead>
            <tbody>
              {runs.data.map((r) => (
                <tr key={r.id}>
                  <td className={td}><Link href={`/app/tasks/${r.id}`} className="text-accent underline underline-offset-2">{r.task_title}</Link>
                    {r.summary && <p className="mt-1 max-w-md text-xs text-muted">{r.summary.slice(0, 160)}</p>}</td>
                  <td className={td}>{r.agent_name}</td>
                  <td className={td}><span className="text-xs">{TRIGGER_LABEL[r.trigger_type] ?? r.trigger_type}</span></td>
                  <td className={td}><RunStatusBadge status={r.status} /></td>
                  <td className={td}><span className="text-xs">{formatDateTime(r.started_at ?? r.created_at)}</span></td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>
    </>
  );
}
