"use client";

import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { ConfigBadge, IssueList, usePolicy } from "@/components/agents/shared";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardHeader, ErrorState, PageHeader, Spinner } from "@/components/ui/display";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { ACCESS_LEVELS, DAY_LABEL, DOC_TYPES, MODE } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type {
  AgentConfigDoc, AgentConfiguration, AgentDetail, AgentTask, Day, PermissionMode, PolicyVocabulary, TaskTrigger,
} from "@/lib/types";

type DraftTask = Omit<AgentTask, "id" | "position" | "trigger_type" | "schedule" | "event"> & { trigger: TaskTrigger; uid: string };
const DAYS: Day[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const MODES: PermissionMode[] = ["denied", "approval_required", "auto"];
const ORDER: Record<PermissionMode, number> = { denied: 0, approval_required: 1, auto: 2 };

let uidCounter = 0;
const uid = () => `t${++uidCounter}`;

function toDraft(t: AgentTask): DraftTask {
  return {
    uid: uid(), key: t.key, title: t.title, description: t.description,
    trigger: { type: t.trigger_type, schedule: t.schedule, event: t.event }, inputs: t.inputs, actions: t.actions,
    expected_output: t.expected_output, completion_criteria: t.completion_criteria, priority: t.priority,
    sla_minutes: t.sla_minutes, policy_refs: t.policy_refs, required_permissions: t.required_permissions,
    approval_required: t.approval_required, approval_reason: t.approval_reason, failure: t.failure, depends_on: t.depends_on,
  };
}

/** The API's TaskIn shape: everything except the editor-only uid. */
function toPayload(t: DraftTask) {
  const out: Record<string, unknown> = { ...t };
  delete out.uid;
  return out;
}

/** One item per line. Keeps the raw text locally so typing a new line isn't swallowed. */
function LinesField({ label, value, onChange, hint, rows = 3 }: { label: string; value: string[]; onChange: (v: string[]) => void; hint?: string; rows?: number }) {
  const [text, setText] = useState(value.join("\n"));
  return (
    <Field label={label} hint={hint ?? "One per line"}>
      {(p) => <Textarea {...p} rows={rows} value={text} onChange={(e) => { setText(e.target.value); onChange(e.target.value.split("\n").map((s) => s.trim()).filter(Boolean)); }} />}
    </Field>
  );
}

function TaskEditor({ task, others, events, scopes, onChange, onRemove }: {
  task: DraftTask; others: DraftTask[]; events: { key: string; label: string }[]; scopes: PolicyVocabulary["scopes"];
  onChange: (t: DraftTask) => void; onRemove: () => void;
}) {
  const set = <K extends keyof DraftTask>(k: K, v: DraftTask[K]) => onChange({ ...task, [k]: v });
  const trig = task.trigger;
  const setTrigger = (type: TaskTrigger["type"]) => set("trigger", type === "schedule"
    ? { type, schedule: trig.schedule ?? { kind: "weekly", days: ["mon", "tue", "wed", "thu", "fri"], time: "10:00" }, event: null }
    : type === "event" ? { type, event: trig.event ?? events[0]?.key ?? null, schedule: null } : { type, schedule: null, event: null });
  const sched = trig.schedule;
  return (
    <Card>
      <CardHeader title={task.title || "New task"} description={`Key: ${task.key}`}
        action={<Button variant="ghost" size="sm" onClick={onRemove} aria-label={`Remove task ${task.title}`}><Trash2 /> Remove</Button>} />
      <div className="grid gap-4 px-5 py-4 md:grid-cols-2">
        <Field label="Title">{(p) => <Input {...p} value={task.title} onChange={(e) => set("title", e.target.value)} />}</Field>
        <Field label="Key" hint="Lowercase letters, digits and hyphens">{(p) => <Input {...p} className="ident" value={task.key} onChange={(e) => set("key", e.target.value)} />}</Field>
        <Field label="Description" className="md:col-span-2">{(p) => <Textarea {...p} rows={2} value={task.description} onChange={(e) => set("description", e.target.value)} />}</Field>
        <Field label="Trigger">
          {(p) => <Select {...p} value={trig.type} onChange={(e) => setTrigger(e.target.value as TaskTrigger["type"])}>
            <option value="schedule">On a schedule</option><option value="event">When an event happens</option><option value="on_demand">Only when asked</option>
          </Select>}
        </Field>
        {trig.type === "event" && (
          <Field label="Event">{(p) => <Select {...p} value={trig.event ?? ""} onChange={(e) => set("trigger", { ...trig, event: e.target.value })}>
            {events.map((e) => <option key={e.key} value={e.key}>{e.label}</option>)}</Select>}</Field>
        )}
        {trig.type === "schedule" && sched && (
          <div className="grid gap-4 sm:grid-cols-3 md:col-span-2">
            <Field label="Repeats">{(p) => <Select {...p} value={sched.kind} onChange={(e) => set("trigger", { ...trig, schedule: e.target.value === "monthly"
              ? { kind: "monthly", day: 1, time: sched.time } : { kind: "weekly", days: ["mon"], time: sched.time } })}>
              <option value="weekly">Weekly</option><option value="monthly">Monthly</option></Select>}</Field>
            <Field label="Time (company time zone)">{(p) => <Input {...p} type="time" value={sched.time} onChange={(e) => set("trigger", { ...trig, schedule: { ...sched, time: e.target.value } })} />}</Field>
            {sched.kind === "monthly" ? (
              <Field label="Day of month" hint="1–28">{(p) => <Input {...p} type="number" min={1} max={28} value={sched.day} onChange={(e) => set("trigger", { ...trig, schedule: { ...sched, day: Number(e.target.value) } })} />}</Field>
            ) : (
              <fieldset className="space-y-1.5">
                <legend className="text-sm font-medium">Days</legend>
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  {DAYS.map((d) => <Checkbox key={d} label={DAY_LABEL[d]} checked={sched.days.includes(d)}
                    onChange={() => set("trigger", { ...trig, schedule: { ...sched, days: sched.days.includes(d) ? sched.days.filter((x) => x !== d) : DAYS.filter((x) => x === d || sched.days.includes(x)) } })} />)}
                </div>
              </fieldset>
            )}
          </div>
        )}
        <LinesField label="Inputs" value={task.inputs} onChange={(v) => set("inputs", v)} />
        <LinesField label="Steps" value={task.actions} onChange={(v) => set("actions", v)} />
        <Field label="Expected output">{(p) => <Textarea {...p} rows={2} value={task.expected_output} onChange={(e) => set("expected_output", e.target.value)} />}</Field>
        <LinesField label="Completion criteria" value={task.completion_criteria} onChange={(v) => set("completion_criteria", v)} />
        <Field label="Priority">{(p) => <Select {...p} value={task.priority} onChange={(e) => set("priority", e.target.value as DraftTask["priority"])}>
          {["low", "normal", "high", "critical"].map((x) => <option key={x} value={x}>{x}</option>)}</Select>}</Field>
        <Field label="Service-level target (minutes, optional)">{(p) => <Input {...p} type="number" min={1} value={task.sla_minutes ?? ""} onChange={(e) => set("sla_minutes", e.target.value ? Number(e.target.value) : null)} />}</Field>
        <fieldset className="space-y-1.5 md:col-span-2">
          <legend className="text-sm font-medium">Permissions this task uses</legend>
          <div className="grid gap-1 sm:grid-cols-2">
            {scopes.map((s) => <Checkbox key={s.key} label={s.label} checked={task.required_permissions.includes(s.key)}
              onChange={() => set("required_permissions", task.required_permissions.includes(s.key) ? task.required_permissions.filter((x) => x !== s.key) : [...task.required_permissions, s.key])} />)}
          </div>
        </fieldset>
        <div className="space-y-2">
          <Checkbox label="Requires a person's approval before acting" checked={task.approval_required} onChange={(e) => set("approval_required", e.target.checked)} />
          {task.approval_required && <Field label="Approval reason">{(p) => <Input {...p} value={task.approval_reason ?? ""} onChange={(e) => set("approval_reason", e.target.value || null)} />}</Field>}
        </div>
        {others.length > 0 && (
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Runs after</legend>
            {others.map((o) => <Checkbox key={o.uid} label={o.title || o.key} checked={task.depends_on.includes(o.key)}
              onChange={() => set("depends_on", task.depends_on.includes(o.key) ? task.depends_on.filter((x) => x !== o.key) : [...task.depends_on, o.key])} />)}
          </fieldset>
        )}
        <div className="grid gap-4 sm:grid-cols-3 md:col-span-2">
          <Field label="Retries">{(p) => <Input {...p} type="number" min={0} max={5} value={task.failure.max_retries} onChange={(e) => set("failure", { ...task.failure, max_retries: Number(e.target.value) })} />}</Field>
          <Field label="Minutes between retries">{(p) => <Input {...p} type="number" min={1} max={1440} value={task.failure.retry_backoff_minutes} onChange={(e) => set("failure", { ...task.failure, retry_backoff_minutes: Number(e.target.value) })} />}</Field>
          <Field label="If it still fails">{(p) => <Select {...p} value={task.failure.on_failure} onChange={(e) => set("failure", { ...task.failure, on_failure: e.target.value as DraftTask["failure"]["on_failure"] })}>
            <option value="escalate">Escalate to a person</option><option value="notify">Notify</option><option value="skip">Skip until next run</option></Select>}</Field>
        </div>
      </div>
    </Card>
  );
}

function Editor({ agent, cfg, vocab, notice, onSaved }: {
  agent: AgentDetail; cfg: AgentConfiguration; vocab: PolicyVocabulary; notice: string | null; onSaved: (c: AgentConfiguration) => void;
}) {
  const [config, setConfig] = useState<AgentConfigDoc>(cfg.config);
  const [tasks, setTasks] = useState<DraftTask[]>(() => cfg.tasks.map(toDraft));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const job = config.job;
  const setJob = <K extends keyof AgentConfigDoc["job"]>(k: K, v: AgentConfigDoc["job"][K]) => setConfig((c) => ({ ...c, job: { ...c.job, [k]: v } }));
  const set = <K extends keyof AgentConfigDoc>(k: K, v: AgentConfigDoc[K]) => setConfig((c) => ({ ...c, [k]: v }));
  const ceiling = (s: PolicyVocabulary["scopes"][number]) =>
    ORDER[s.max_mode] < ORDER[agent.definition.permission_ceilings[s.key]] ? s.max_mode : agent.definition.permission_ceilings[s.key];
  const events = vocab.events.filter((e) => agent.definition.supported_events.includes(e.key));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = { config, tasks: tasks.map(toPayload) };
      onSaved(await api<AgentConfiguration>(`/api/v1/agents/${agent.id}/config/draft`, { method: "PUT", org: true, body }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const addTask = () => {
    const keys = new Set(tasks.map((t) => t.key));
    let n = tasks.length + 1;
    while (keys.has(`task-${n}`)) n++;
    setTasks([...tasks, { uid: uid(), key: `task-${n}`, title: "", description: "", trigger: { type: "on_demand" }, inputs: [], actions: [],
      expected_output: "", completion_criteria: [], priority: "normal", sla_minutes: null, policy_refs: [], required_permissions: ["data.read"],
      approval_required: false, approval_reason: null, depends_on: [], failure: { max_retries: 2, retry_backoff_minutes: 15, on_failure: "escalate" } }]);
  };

  return (
    <form className="space-y-6" onSubmit={(e) => { e.preventDefault(); void save(); }}>
      {cfg.status !== "draft" && (
        <Alert tone="warning" title={`Version ${cfg.version} is ${cfg.status === "submitted" ? "waiting for approval" : cfg.status}`}>
          Saving creates version {cfg.version + 1} as a new draft{cfg.status === "approved" ? " that needs approval again" : ""}.
        </Alert>
      )}
      <Card>
        <CardHeader title="Job description" />
        <div className="grid gap-4 px-5 py-4 md:grid-cols-2">
          <Field label="Job title">{(p) => <Input {...p} value={job.title} onChange={(e) => setJob("title", e.target.value)} />}</Field>
          <Field label="Department">{(p) => <Input {...p} value={job.department} onChange={(e) => setJob("department", e.target.value)} />}</Field>
          <Field label="Mission" className="md:col-span-2">{(p) => <Textarea {...p} rows={3} value={job.mission} onChange={(e) => setJob("mission", e.target.value)} />}</Field>
          <Field label="Scope of responsibility" className="md:col-span-2">{(p) => <Textarea {...p} rows={2} value={job.scope} onChange={(e) => setJob("scope", e.target.value)} />}</Field>
          <LinesField label="Included tasks" value={job.included_tasks} onChange={(v) => setJob("included_tasks", v)} rows={5} />
          <LinesField label="Excluded tasks" value={job.excluded_tasks} onChange={(v) => setJob("excluded_tasks", v)} rows={5} />
          <LinesField label="Escalation policies" value={job.escalation_policies} onChange={(v) => setJob("escalation_policies", v)} />
          <LinesField label="Approval requirements" value={job.approval_requirements} onChange={(v) => setJob("approval_requirements", v)} />
          <LinesField label="Priority rules" value={job.priority_rules} onChange={(v) => setJob("priority_rules", v)} />
          <LinesField label="Success metrics" value={job.success_metrics} onChange={(v) => setJob("success_metrics", v)} />
          <LinesField label="Required knowledge" value={job.required_knowledge} onChange={(v) => setJob("required_knowledge", v)} />
          <LinesField label="Permitted data sources" value={job.data_sources} onChange={(v) => setJob("data_sources", v)} />
          <LinesField label="Dependencies" value={job.dependencies} onChange={(v) => setJob("dependencies", v)} />
        </div>
      </Card>

      <Card>
        <CardHeader title="Operating schedule" description="Monitoring (noticing events) is separate from when routine work may run." />
        <div className="grid gap-4 px-5 py-4 md:grid-cols-2">
          <Field label="Operating mode">{(p) => <Select {...p} value={config.operating.mode} onChange={(e) => set("operating", { ...config.operating, mode: e.target.value as AgentConfigDoc["operating"]["mode"] })}>
            {vocab.operating_modes.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}</Select>}</Field>
          <Field label="Monitoring">{(p) => <Select {...p} value={config.operating.monitoring} onChange={(e) => set("operating", { ...config.operating, monitoring: e.target.value as AgentConfigDoc["operating"]["monitoring"] })}>
            <option value="continuous">Continuous (24/7)</option><option value="business_hours">Business hours</option><option value="off">Off</option></Select>}</Field>
          <Field label="Routine work may run">{(p) => <Select {...p} value={config.operating.execution_window} onChange={(e) => set("operating", { ...config.operating, execution_window: e.target.value as AgentConfigDoc["operating"]["execution_window"] })}>
            <option value="business_hours">Only in business hours</option><option value="any_time">At any time</option></Select>}</Field>
          <Field label="Critical alerts">{(p) => <Select {...p} value={config.operating.critical_alerts} onChange={(e) => set("operating", { ...config.operating, critical_alerts: e.target.value as AgentConfigDoc["operating"]["critical_alerts"] })}>
            <option value="immediate">Immediately, at any hour</option><option value="next_business_day">Next business day</option></Select>}</Field>
          <Field label="Reporting cadence">{(p) => <Select {...p} value={config.reporting.cadence} onChange={(e) => set("reporting", { ...config.reporting, cadence: e.target.value as AgentConfigDoc["reporting"]["cadence"] })}>
            <option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></Select>}</Field>
          <Field label="Report notes (optional)">{(p) => <Input {...p} value={config.reporting.notes} onChange={(e) => set("reporting", { ...config.reporting, notes: e.target.value })} />}</Field>
        </div>
      </Card>

      <Card>
        <CardHeader title="Permissions & tools" description="Options above this agent's limits are not available. Approval is enforced by the platform, not just hidden in the interface." />
        <div className="space-y-5 px-5 py-4">
          <Field label="Automation level">{(p) => <Select {...p} value={config.automation_level} onChange={(e) => set("automation_level", e.target.value as AgentConfigDoc["automation_level"])}>
            {vocab.automation_levels.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}</Select>}</Field>
          <div className="grid gap-4 md:grid-cols-2">
            {vocab.scopes.map((s) => (
              <Field key={s.key} label={s.label} hint={`Risk: ${s.risk}`}>
                {(p) => <Select {...p} value={config.permissions[s.key]} onChange={(e) => set("permissions", { ...config.permissions, [s.key]: e.target.value as PermissionMode })}>
                  {MODES.map((m) => <option key={m} value={m} disabled={ORDER[m] > ORDER[ceiling(s)]}>{MODE[m].label}{ORDER[m] > ORDER[ceiling(s)] ? " (not allowed)" : ""}</option>)}
                </Select>}
              </Field>
            ))}
          </div>
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Authorised tools</legend>
            {agent.definition.tools.map((t) => <Checkbox key={t.key} label={t.label} hint={`Needs: ${vocab.scopes.find((s) => s.key === t.scope)?.label}`}
              checked={job.authorized_tools.includes(t.key)}
              onChange={() => setJob("authorized_tools", job.authorized_tools.includes(t.key) ? job.authorized_tools.filter((k) => k !== t.key) : [...job.authorized_tools, t.key])} />)}
          </fieldset>
        </div>
      </Card>

      <Card>
        <CardHeader title="Knowledge, model & limits" />
        <div className="grid gap-5 px-5 py-4 md:grid-cols-2">
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Document types</legend>
            <div className="grid grid-cols-2 gap-1">
              {DOC_TYPES.map(([k, l]) => <Checkbox key={k} label={l} checked={config.knowledge.doc_types.includes(k)}
                onChange={() => set("knowledge", { ...config.knowledge, doc_types: config.knowledge.doc_types.includes(k) ? config.knowledge.doc_types.filter((x) => x !== k) : [...config.knowledge.doc_types, k] })} />)}
            </div>
          </fieldset>
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Access levels</legend>
            {ACCESS_LEVELS.map(([k, l, help]) => <Checkbox key={k} label={l} hint={help} checked={config.knowledge.access_levels.includes(k)}
              onChange={() => set("knowledge", { ...config.knowledge, access_levels: config.knowledge.access_levels.includes(k) ? config.knowledge.access_levels.filter((x) => x !== k) : [...config.knowledge.access_levels, k] })} />)}
          </fieldset>
          <Field label="Model">{(p) => <Select {...p} value={config.model.tier} onChange={(e) => set("model", { ...config.model, tier: e.target.value as AgentConfigDoc["model"]["tier"] })}>
            <option value="reasoning">Reasoning (more capable)</option><option value="fast">Fast (cheaper)</option></Select>}</Field>
          <Field label="Effort">{(p) => <Select {...p} value={config.model.effort} onChange={(e) => set("model", { ...config.model, effort: e.target.value as AgentConfigDoc["model"]["effort"] })}>
            <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></Select>}</Field>
          <Field label="Monthly budget (USD)">{(p) => <Input {...p} type="number" min={0} step="0.01" value={config.limits.monthly_budget_usd} onChange={(e) => set("limits", { ...config.limits, monthly_budget_usd: e.target.value })} />}</Field>
          <Field label="Maximum runs per day">{(p) => <Input {...p} type="number" min={1} max={1000} value={config.limits.max_runs_per_day} onChange={(e) => set("limits", { ...config.limits, max_runs_per_day: Number(e.target.value) })} />}</Field>
        </div>
      </Card>

      <section aria-labelledby="tasks-h" className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 id="tasks-h" className="text-sm font-semibold">Tasks ({tasks.length})</h2>
          <Button variant="secondary" size="sm" onClick={addTask}><Plus /> Add task</Button>
        </div>
        {tasks.map((t, i) => (
          <TaskEditor key={t.uid} task={t} others={tasks.filter((o) => o.uid !== t.uid)} events={events} scopes={vocab.scopes}
            onChange={(nt) => setTasks(tasks.map((x, j) => (j === i ? nt : x)))} onRemove={() => setTasks(tasks.filter((_, j) => j !== i))} />
        ))}
      </section>

      <div className="sticky bottom-0 -mx-4 space-y-3 border-t border-border bg-bg/95 px-4 py-4 backdrop-blur sm:-mx-6 sm:px-6 lg:-mx-10 lg:px-10">
        {error && <Alert tone="danger">{error}</Alert>}
        {notice && <><Alert tone="success">{notice}</Alert><IssueList issues={cfg.issues} /></>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" loading={busy}><Save /> Save draft</Button>
          <Link href={`/app/agents/${agent.id}`} className="inline-flex h-9 items-center px-3 text-sm text-muted hover:text-fg">Back to agent</Link>
        </div>
      </div>
    </form>
  );
}

export default function ConfigurePage() {
  const { id } = useParams<{ id: string }>();
  const { orgId, can } = useSession();
  const { mutate } = useSWRConfig();
  const path = `/api/v1/agents/${id}`;
  const { data: agent, error } = useOrgData<AgentDetail>(path);
  const { data: vocab, error: vErr } = usePolicy();
  const [notice, setNotice] = useState<string | null>(null);
  if (error || vErr) return <ErrorState error={(error ?? vErr)!} />;
  if (!agent || !vocab) return <Spinner />;
  const cfg = agent.current_config;
  return (
    <>
      <Link href={`/app/agents/${id}`} className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-fg"><ArrowLeft className="size-4" /> {agent.name}</Link>
      <PageHeader title={`Configure ${agent.name}`}
        description="Everything here is reviewed by the CEO before the agent can be tested or activated."
        actions={cfg && <ConfigBadge status={cfg.status} />} />
      {!can("agent.configure") ? <Alert tone="warning">Only managers, admins and owners can edit agent configurations.</Alert>
        : !cfg ? <Alert tone="info">Generate a job description on the <Link href={`/app/agents/${id}`} className="underline">agent page</Link> first.</Alert>
        : (
          <>
            <div className="mb-6"><IssueList issues={cfg.issues} /></div>
            <Editor key={cfg.id} agent={agent} cfg={cfg} vocab={vocab} notice={notice}
              onSaved={(c) => {
                setNotice(`Saved as version ${c.version} (draft).`);
                return Promise.all([path, `${path}/config/versions`, `${path}/schedule`].map((p) => mutate([p, orgId])));
              }} />
          </>
        )}
    </>
  );
}
