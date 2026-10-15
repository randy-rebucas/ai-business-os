"use client";

import { ArrowLeft, Check, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { ActionCard } from "@/components/execution/action-card";
import { ExecutionTable, isActive, RunStatusBadge } from "@/components/execution/shared";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardHeader, ErrorState, Meta, PageHeader, Spinner } from "@/components/ui/display";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { pollWhile, useOrgData } from "@/lib/hooks";
import { RUN_STATUS, TRIGGER_LABEL } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { WorkflowRunDetail } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

function Finding({ f }: { f: Record<string, unknown> | string }) {
  if (typeof f === "string") return <>{f}</>;
  const { invoice_id: _i, run_id: runId, expense_id: _e, ...rest } = f;
  void _i; void _e;
  const text = Object.entries(rest).map(([k, v]) => `${k.replaceAll("_", " ")}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join(" · ");
  return runId ? <Link href={`/app/tasks/${runId}`} className="text-accent underline underline-offset-2">{text}</Link> : <>{text}</>;
}

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const path = `/api/v1/workflows/${id}`;
  const { data: run, error } = useOrgData<WorkflowRunDetail>(path, pollWhile<WorkflowRunDetail>((r) => isActive(r), 1500));
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  if (error) return <ErrorState error={error} />;
  if (!run) return <Spinner />;
  const refresh = () => mutate([path, orgId]);
  const cancel = async () => {
    setBusy(true);
    setActionError(null);
    try {
      await api(`${path}/cancel`, { method: "POST", org: true });
      await refresh();
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const checks = run.validation.checks ?? [];
  const missing = run.output.missing_evidence ?? [];
  const findings = run.output.findings ?? [];
  const cancellable = ["queued", "awaiting_approval", "waiting_children"].includes(run.status) && can("task.manage");
  return (
    <>
      <Link href={run.parent ? `/app/tasks/${run.parent.run_id}` : "/app/tasks"} className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-fg">
        <ArrowLeft className="size-4" /> {run.parent ? run.parent.task_title : "Tasks"}
      </Link>
      <PageHeader context={`${run.agent_name} · ${TRIGGER_LABEL[run.trigger_type] ?? run.trigger_type}`} title={run.task_title}
        description={RUN_STATUS[run.status]?.help} actions={<>
          <RunStatusBadge status={run.status} />
          {cancellable && <Button size="sm" variant="secondary" onClick={cancel} loading={busy}>Cancel run</Button>}
        </>} />
      {actionError && <Alert tone="danger" className="mb-6">{actionError}</Alert>}
      <div className="space-y-6">
        {run.planner.label && <Alert tone="warning" title="Development mode">{run.planner.label}</Alert>}
        {run.status_reason && !isActive(run) && run.status !== "completed" && <Alert tone={RUN_STATUS[run.status]?.tone === "danger" ? "danger" : "warning"} title={RUN_STATUS[run.status]?.label}>{run.status_reason}</Alert>}
        {run.action_requests.some((a) => a.status === "pending") && (
          <section aria-labelledby="actions-h" className="space-y-3">
            <h2 id="actions-h" className="text-sm font-semibold">Waiting for your decision</h2>
            {run.action_requests.filter((a) => a.status === "pending").map((a) => (
              <ActionCard key={a.id} req={a} canDecide={can("approval.decide")} onDecided={refresh} />
            ))}
          </section>
        )}
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <Card>
            <CardHeader title="Result" description="Written from the tool results below. Every figure must appear in one of them." />
            <div className="space-y-4 px-5 py-4 text-sm">
              {run.request && <p className="text-muted">Request: “{run.request}”</p>}
              <p className="whitespace-pre-line text-fg">{run.output.summary || (isActive(run) ? "Working…" : "No summary.")}</p>
              {findings.length > 0 && (
                <ul className="list-disc space-y-1 pl-5">{findings.map((f, i) => <li key={i}><Finding f={f} /></li>)}</ul>
              )}
              {missing.length > 0 && (
                <Alert tone="warning" title="Missing evidence (not filled in)">
                  <ul className="list-disc pl-4">{missing.map((m) => <li key={m}>{m}</li>)}</ul>
                </Alert>
              )}
            </div>
          </Card>
          <div className="space-y-6">
            <Card>
              <CardHeader title="Checks" description="Deterministic validation — no model judges the result." />
              {checks.length === 0 ? <p className="px-5 py-3 text-sm text-muted">{isActive(run) ? "Runs when the task finishes." : "None recorded."}</p> : (
                <ul className="divide-y divide-border">
                  {checks.map((c) => (
                    <li key={c.label} className="flex gap-3 px-5 py-2.5 text-sm">
                      {c.ok ? <Check aria-label="Passed" className="mt-0.5 size-4 shrink-0 text-success" /> : <X aria-label="Failed" className="mt-0.5 size-4 shrink-0 text-danger" />}
                      <span><span className="text-fg">{c.label}</span><span className="block text-xs text-muted">{c.detail}</span></span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <CardHeader title="Run" />
              <dl className="px-5 py-3">
                <Meta label="Configuration">v{run.config_version}</Meta>
                <Meta label="Fingerprint" mono>{run.config_hash.slice(0, 12)}</Meta>
                <Meta label="Policy" mono>{run.policy_version}</Meta>
                <Meta label="Planner">{run.planner.mode === "model" ? `${run.planner.provider} · ${run.planner.model}` : run.planner.mode ? "Playbook" : "—"}</Meta>
                <Meta label="Queued">{formatDateTime(run.created_at)}</Meta>
                {run.not_before && <Meta label="Deferred until">{formatDateTime(run.not_before)}</Meta>}
                <Meta label="Finished">{formatDateTime(run.finished_at)}</Meta>
              </dl>
            </Card>
          </div>
        </div>
        {run.children.length > 0 && (
          <Card>
            <CardHeader title="Delegated to" description="Each agent ran its own read-only request task. Delegated runs can't delegate further." />
            <ul className="divide-y divide-border">
              {run.children.map((c) => (
                <li key={c.run_id} className="flex flex-wrap items-start justify-between gap-3 px-5 py-3 text-sm">
                  <span><Link href={`/app/tasks/${c.run_id}`} className="font-medium text-accent underline underline-offset-2">{c.agent}</Link>
                    <span className="block text-xs text-muted">{c.summary || c.reason || "—"}</span></span>
                  <RunStatusBadge status={c.status} />
                </li>
              ))}
            </ul>
          </Card>
        )}
        <section aria-labelledby="ledger-h" className="space-y-3">
          <h2 id="ledger-h" className="text-sm font-semibold">Execution evidence ({run.executions.length} recorded calls)</h2>
          {run.executions.length === 0 ? <p className="text-sm text-muted">No calls yet.</p> : <ExecutionTable rows={run.executions} label="Tool executions" />}
        </section>
        {run.action_requests.some((a) => a.status !== "pending") && (
          <section aria-labelledby="decided-h" className="space-y-3">
            <h2 id="decided-h" className="text-sm font-semibold">Approval history</h2>
            {run.action_requests.filter((a) => a.status !== "pending").map((a) => (
              <ActionCard key={a.id} req={a} canDecide={false} onDecided={refresh} />
            ))}
          </section>
        )}
      </div>
    </>
  );
}
