"use client";

import { FlaskConical, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { RunBadge } from "@/components/simulation/shared";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { SCENARIO_CATEGORY } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { AgentDefinition, Scenario, SimulationRun } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const PROBES = ["payment.execute", "refund.execute", "transaction.approve", "bank_details.update", "record.delete"];

function CustomScenario({ agent, onDone }: { agent: AgentDefinition; onDone: () => void }) {
  const [f, setF] = useState({ title: "", category: "normal", request: "", question: "", expected_answer_contains: "",
    answer_must_not_contain: "", must_escalate: false, forbidden_tool: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f, v: string | boolean) => setF((x) => ({ ...x, [k]: v }));
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const blank = (v: string) => v.trim() || null;
      await api("/api/v1/simulations/scenarios", { method: "POST", org: true, body: {
        agent_key: agent.key, category: f.category, title: f.title, request: f.request, question: blank(f.question),
        expected_answer_contains: blank(f.expected_answer_contains), answer_must_not_contain: blank(f.answer_must_not_contain),
        must_escalate: f.must_escalate, forbidden_tool: blank(f.forbidden_tool) } });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="mb-6">
      <CardHeader title={`New scenario for the ${agent.name}`} description="Describe the situation and what must (or must never) happen. The platform turns it into deterministic checks." />
      <form className="grid gap-4 px-5 py-4 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <Field label="Title">{(p) => <Input {...p} value={f.title} onChange={(e) => set("title", e.target.value)} />}</Field>
        <Field label="Category">{(p) => <Select {...p} value={f.category} onChange={(e) => set("category", e.target.value)}>
          {Object.entries(SCENARIO_CATEGORY).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}</Field>
        <Field label="What happens (the request or event)" className="md:col-span-2">{(p) => <Textarea {...p} rows={2} value={f.request} onChange={(e) => set("request", e.target.value)} />}</Field>
        <Field label="Question the agent must answer from knowledge (optional)">{(p) => <Input {...p} value={f.question} onChange={(e) => set("question", e.target.value)} />}</Field>
        <Field label="Answer must mention (optional)">{(p) => <Input {...p} value={f.expected_answer_contains} onChange={(e) => set("expected_answer_contains", e.target.value)} />}</Field>
        <Field label="Must never say (optional)">{(p) => <Input {...p} value={f.answer_must_not_contain} onChange={(e) => set("answer_must_not_contain", e.target.value)} />}</Field>
        <Field label="Action that must never run (optional)">{(p) => <Select {...p} value={f.forbidden_tool} onChange={(e) => set("forbidden_tool", e.target.value)}>
          <option value="">None</option>
          {[...agent.tools.map((t) => t.key), ...PROBES].map((k) => <option key={k} value={k}>{k}</option>)}</Select>}</Field>
        <Checkbox label="Must escalate to a person" checked={f.must_escalate} onChange={(e) => set("must_escalate", e.target.checked)} />
        {error && <Alert tone="danger" className="md:col-span-2">{error}</Alert>}
        <div className="md:col-span-2"><Button type="submit" loading={busy} disabled={!f.title.trim() || f.request.trim().length < 3}>Add scenario</Button></div>
      </form>
    </Card>
  );
}

function Library({ agent }: { agent: AgentDefinition }) {
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const path = `/api/v1/simulations/scenarios?agent_key=${agent.key}`;
  const { data, error } = useOrgData<Scenario[]>(path);
  const [adding, setAdding] = useState(false);
  const refresh = () => mutate([path, orgId]);
  const remove = async (s: Scenario) => {
    await api(`/api/v1/simulations/scenarios/${s.id}`, { method: "DELETE", org: true });
    await refresh();
  };
  if (error) return <ErrorState error={error} />;
  if (!data) return <Spinner />;
  const active = data.filter((s) => s.is_active);
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted">{active.length} scenarios · {new Set(active.map((s) => s.category)).size} of 14 categories</p>
        {can("simulation.run") && !adding && <Button size="sm" variant="secondary" onClick={() => setAdding(true)}><Plus /> Add scenario</Button>}
      </div>
      {adding && <CustomScenario agent={agent} onDone={() => { setAdding(false); void refresh(); }} />}
      <Table label={`Scenarios for the ${agent.name}`}>
        <thead><tr><th className={th}>Scenario</th><th className={th}>Category</th><th className={th}>Expected</th><th className={th}>Checks</th><th className={th}></th></tr></thead>
        <tbody>
          {active.map((s) => (
            <tr key={s.id}>
              <td className={td}><span className="font-medium">{s.title}</span>
                <div className="flex gap-1.5 pt-1">{s.source === "custom" && <Badge tone="info">Custom</Badge>}{s.required && <Badge>Required</Badge>}</div></td>
              <td className={td}>{SCENARIO_CATEGORY[s.category] ?? s.category}</td>
              <td className={td}><span className="text-xs">{s.expected_outcome}</span></td>
              <td className={td}>{s.assertions.length}{s.assertions.some((a) => a.mandatory) && <span className="block text-xs text-muted">incl. security</span>}</td>
              <td className={td}>{s.source === "custom" && can("simulation.run") && <Button size="sm" variant="ghost" onClick={() => remove(s)}>Remove</Button>}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

export default function SimulationCenterPage() {
  const runs = useOrgData<SimulationRun[]>("/api/v1/simulations/runs");
  const catalog = useOrgData<AgentDefinition[]>("/api/v1/agents/catalog");
  const [key, setKey] = useState<string>("");
  const agent = catalog.data?.find((d) => d.key === (key || catalog.data?.find((x) => x.status !== "available")?.key || "finance"));
  return (
    <>
      <PageHeader title="Simulation & evaluation"
        description="Business scenarios every AI employee is tested against before it may act — including attempts to break the rules. Runs happen in a sandbox." />
      <section aria-labelledby="runs-h" className="mb-10">
        <h2 id="runs-h" className="mb-3 text-sm font-semibold">Recent runs</h2>
        {runs.error ? <ErrorState error={runs.error} /> : !runs.data ? <Spinner /> : runs.data.length === 0 ? (
          <EmptyState icon={FlaskConical} title="No runs yet">Open an agent&apos;s readiness page to run its tests.</EmptyState>
        ) : (
          <Table label="Simulation runs">
            <thead><tr><th className={th}>Agent</th><th className={th}>Configuration</th><th className={th}>Result</th><th className={th}>Scenarios</th><th className={th}>Started</th></tr></thead>
            <tbody>
              {runs.data.map((r) => (
                <tr key={r.id}>
                  <td className={td}><Link href={`/app/simulations/runs/${r.id}`} className="text-accent underline underline-offset-2">{r.agent_name}</Link></td>
                  <td className={td}>v{r.config_version}</td>
                  <td className={td}><RunBadge run={r} /></td>
                  <td className={td}>{r.summary.scenarios ? `${r.summary.passed} / ${r.summary.scenarios}` : "—"}</td>
                  <td className={td}><span className="text-xs">{formatDateTime(r.created_at)}</span></td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>
      <section aria-labelledby="lib-h">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <h2 id="lib-h" className="text-sm font-semibold">Scenario library</h2>
          {catalog.data && (
            <Field label="Agent" className="w-72">{(p) => <Select {...p} value={agent?.key ?? ""} onChange={(e) => setKey(e.target.value)}>
              {catalog.data!.map((d) => <option key={d.key} value={d.key}>{d.name}</option>)}</Select>}</Field>
          )}
        </div>
        {catalog.error ? <ErrorState error={catalog.error} /> : !agent ? <Spinner /> : <Library key={agent.key} agent={agent} />}
      </section>
    </>
  );
}
