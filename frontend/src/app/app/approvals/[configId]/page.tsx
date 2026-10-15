"use client";

import { ArrowLeft, Check, Undo2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";

import {
  ConfigBadge, GenerationNotes, IssueList, JobView, KnowledgeView, PermissionsView, ResponsibilitiesView, TaskView, usePolicy,
} from "@/components/agents/shared";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardHeader, ErrorState, Meta, PageHeader, Spinner } from "@/components/ui/display";
import { Field, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { money } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { AgentConfiguration, AgentDetail } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-3">
      <h2 id={id} className="text-base font-semibold text-fg">{title}</h2>
      {children}
    </section>
  );
}

function Decision({ cfg, onDone }: { cfg: AgentConfiguration; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const errors = cfg.issues.filter((i) => i.severity === "error").length;
  const decide = async (decision: "approved" | "rejected") => {
    setBusy(decision);
    setError(null);
    try {
      await api(`/api/v1/approvals/configurations/${cfg.id}/decide`, { method: "POST", org: true,
        body: { decision, note: note.trim() || null, config_hash: cfg.config_hash } });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
      setBusy(null);
    }
  };
  return (
    <Card className="border-accent/40">
      <CardHeader title="Your decision" description={`Binds to configuration v${cfg.version}, fingerprint ${cfg.config_hash.slice(0, 12)}…, and the current policy version.`} />
      <div className="space-y-3 px-5 py-4">
        <Field label="Note" hint="Required when requesting changes.">{(p) => <Textarea {...p} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => decide("approved")} loading={busy === "approved"} disabled={!!busy || errors > 0}><Check /> Approve configuration</Button>
          <Button variant="danger" onClick={() => decide("rejected")} loading={busy === "rejected"} disabled={!!busy || !note.trim()}><Undo2 /> Request changes</Button>
        </div>
        <p className="text-xs text-subtle">Approval moves the agent to readiness testing. It can&apos;t act on business systems until it passes testing and is activated.</p>
      </div>
    </Card>
  );
}

export default function ApprovalSummaryPage() {
  const { configId } = useParams<{ configId: string }>();
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const path = `/api/v1/approvals/configurations/${configId}`;
  const { data: cfg, error } = useOrgData<AgentConfiguration>(path);
  const { data: agent, error: aErr } = useOrgData<AgentDetail>(cfg ? `/api/v1/agents/${cfg.instance_id}` : null);
  const { data: vocab } = usePolicy();
  const [done, setDone] = useState(false);
  if (error || aErr) return <ErrorState error={(error ?? aErr)!} />;
  if (!cfg || !agent) return <Spinner />;
  const c = cfg.config;
  const refresh = () => {
    setDone(true);
    return Promise.all([path, `/api/v1/agents/${cfg.instance_id}`, "/api/v1/approvals/pending", "/api/v1/approvals"].map((p) => mutate([p, orgId])));
  };
  return (
    <>
      <Link href="/app/approvals" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-fg"><ArrowLeft className="size-4" /> Approval inbox</Link>
      <PageHeader eyebrow="Approval summary" title={`${agent.name} — configuration v${cfg.version}`}
        description="Everything this agent would be allowed to do. Review it as a whole: the decision covers exactly this version."
        actions={<ConfigBadge status={cfg.status} />} />
      {done && <Alert tone="success" className="mb-6">Decision recorded.</Alert>}
      <div className="space-y-10">
        <div className="space-y-3"><IssueList issues={cfg.issues} /><GenerationNotes generation={cfg.generation} /></div>
        <Card>
          <CardHeader title="Summary" />
          <dl className="grid gap-x-8 px-5 py-3 sm:grid-cols-2">
            <Meta label="Automation level">{vocab?.automation_levels.find((a) => a.key === c.automation_level)?.label ?? c.automation_level}</Meta>
            <Meta label="Operating mode">{vocab?.operating_modes.find((m) => m.key === c.operating.mode)?.label ?? c.operating.mode}</Meta>
            <Meta label="Routine work">{c.operating.execution_window === "business_hours" ? "Business hours only" : "Any time"}; monitoring {c.operating.monitoring.replace("_", " ")}</Meta>
            <Meta label="Critical alerts">{c.operating.critical_alerts === "immediate" ? "Immediately" : "Next business day"}</Meta>
            <Meta label="Usage budget">{money(c.limits.monthly_budget_usd)} / month · max {c.limits.max_runs_per_day} runs/day</Meta>
            <Meta label="Reporting">{c.reporting.cadence}</Meta>
            <Meta label="Submitted">{cfg.submitted_at ? formatDateTime(cfg.submitted_at) : null}</Meta>
            <Meta label="Fingerprint" mono>{cfg.config_hash.slice(0, 16)}</Meta>
          </dl>
        </Card>
        <Section id="s-job" title="Job description"><JobView config={c} /></Section>
        <Section id="s-resp" title="Responsibilities, escalation & metrics"><ResponsibilitiesView config={c} /></Section>
        <Section id="s-tasks" title={`Task assignments (${cfg.tasks.length})`}>
          {cfg.tasks.map((t) => <TaskView key={t.id} task={t} events={vocab?.events} />)}
        </Section>
        <Section id="s-know" title="Business knowledge access"><KnowledgeView config={c} generation={cfg.generation} /></Section>
        <Section id="s-perm" title="Tools & permissions"><PermissionsView config={c} definition={agent.definition} vocab={vocab} /></Section>
        {cfg.status === "submitted" && can("approval.decide") && !done && <Decision cfg={cfg} onDone={refresh} />}
        {cfg.status === "submitted" && !can("approval.decide") && <Alert tone="info">Only workspace owners can approve agent configurations.</Alert>}
      </div>
    </>
  );
}
