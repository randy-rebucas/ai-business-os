"use client";

import { ArrowLeft, ArrowRight, Check, Pause, Play, Rocket, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { LifecycleBadge } from "@/components/agents/shared";
import { isRunning, RunBadge } from "@/components/simulation/shared";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/form";
import { api, ApiError } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { pollWhile, useOrgData } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { AgentDetail, Readiness, SimulationRun } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

function describe(err: unknown): string {
  if (err instanceof ApiError && Array.isArray(err.details)) {
    const items = (err.details as { label?: string; detail?: string }[]).filter((d) => d.label);
    if (items.length) return `${err.message}: ${items.map((d) => `${d.label} — ${d.detail}`).join("; ")}`;
  }
  return errorMessage(err);
}

const NEXT: Record<string, { step: string; unlocks: string }> = {
  approved: { step: "Get the current configuration approved by the owner.", unlocks: "readiness testing" },
  tested: { step: "Run the readiness tests on this exact configuration.", unlocks: "a pass or fail verdict" },
  passed: { step: "Fix what the last run failed — its suggestions can be applied as a new version.", unlocks: "activation" },
  policy: { step: "Re-run the tests: confirmed business rules changed since the last run.", unlocks: "resuming or widening" },
  coverage: { step: "Re-run the tests: required scenarios were added or updated.", unlocks: "activation" },
};

/** Only the next decision ahead, and what it unlocks — not the whole map. */
function NextStep({ gate, status, stage }: { gate: Readiness; status: string; stage: string | null }) {
  const blocker = gate.items.find((i) => !i.ok);
  const next = blocker ? NEXT[blocker.key] ?? { step: blocker.detail, unlocks: "activation" }
    : status === "ready_for_deployment" ? { step: "Activate in observation mode.", unlocks: "real, read-only work with evidence" }
      : status === "active" && stage === "observation" ? { step: "When the observation period is over, give it full approved permissions.", unlocks: "its approved actions" }
        : status === "paused" ? { step: "Resume the agent.", unlocks: "its scheduled work" } : null;
  if (!next) return null;
  return (
    <section aria-label="Next step" className="mb-6 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-y-2 border-rule py-3">
      <ArrowRight aria-hidden className="size-4 self-center text-accent" />
      <h2 className="font-display text-base font-bold">{next.step}</h2>
      <p className="text-sm text-muted">Unlocks {next.unlocks}.</p>
    </section>
  );
}

export default function ReadinessPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const base = `/api/v1/agents/${id}`;
  const agentQ = useOrgData<AgentDetail>(base);
  const gateQ = useOrgData<Readiness>(`${base}/readiness`);
  const runsQ = useOrgData<SimulationRun[]>(`${base}/simulations`, pollWhile<SimulationRun[]>((rs) => rs.some(isRunning), 2000));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const refresh = () => Promise.all([base, `${base}/readiness`, `${base}/simulations`].map((p) => mutate([p, orgId])));

  const act = async (key: string, path: string, body?: unknown) => {
    setBusy(key);
    setError(null);
    try {
      const out = await api<{ id: string }>(path, { method: "POST", org: true, body });
      if (key === "run") router.push(`/app/simulations/runs/${out.id}`);
      else await refresh();
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(null);
    }
  };

  if (agentQ.error || gateQ.error) return <ErrorState error={(agentQ.error ?? gateQ.error)!} />;
  if (!agentQ.data || !gateQ.data) return <Spinner />;
  const agent = agentQ.data;
  const gate = gateQ.data;
  const hash = gate.config_hash;
  const running = runsQ.data?.some(isRunning);
  return (
    <>
      <Link href={`/app/agents/${id}`} className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-fg"><ArrowLeft className="size-4" /> {agent.name}</Link>
      <PageHeader title={`Is ${agent.name} ready?`}
        description="An agent is tested against business scenarios in a sandbox before it may act. Activation is your decision and always starts in observation mode."
        actions={<>
          <LifecycleBadge status={agent.status} />
          {agent.deployment_stage && <Badge tone={agent.deployment_stage === "full" ? "success" : "info"}>{agent.deployment_stage === "full" ? "Full permissions" : "Observation mode"}</Badge>}
        </>} />
      {error && <Alert tone="danger" className="mb-6">{error}</Alert>}
      <NextStep gate={gate} status={agent.status} stage={agent.deployment_stage} />
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <CardHeader title="Readiness checklist" description={gate.ready ? "All conditions are met." : "Every item must pass before activation."}
            action={can("simulation.run") && agent.current_config && agent.status !== "retired" && (
              <Button size="sm" onClick={() => act("run", `${base}/simulations`)} loading={busy === "run"} disabled={!!busy || running}><ShieldCheck /> Run readiness tests</Button>
            )} />
          <ul className="divide-y divide-border">
            {gate.items.map((i) => (
              <li key={i.key} className="flex gap-3 px-5 py-3 text-sm">
                {i.ok ? <Check aria-label="Done" className="mt-0.5 size-4 shrink-0 text-success" /> : <X aria-label="Not done" className="mt-0.5 size-4 shrink-0 text-danger" />}
                <span><span className="text-fg">{i.label}</span><span className="block text-xs text-muted">{i.detail}</span></span>
              </li>
            ))}
          </ul>
        </Card>
        <div className="space-y-6">
          {agent.status === "ready_for_deployment" && can("agent.activate") && hash && (
            <Card className="border-accent/40">
              <CardHeader title="Activate" description="Starts in observation mode: the agent may read and prepare drafts only, whatever its configuration allows." />
              <div className="space-y-3 px-5 py-4">
                <Field label="Note (optional)">{(p) => <Input {...p} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
                <Button onClick={() => act("activate", `${base}/activate`, { config_hash: hash, note: note || null })} loading={busy === "activate"} disabled={!!busy || !gate.ready}><Rocket /> Activate in observation mode</Button>
              </div>
            </Card>
          )}
          {agent.status === "active" && agent.deployment_stage === "observation" && can("agent.activate") && hash && (
            <Card>
              <CardHeader title="Widen to full permissions" description="After the observation period, re-run the tests; then the approved permissions can take effect." />
              <div className="px-5 py-4">
                <Button variant="secondary" onClick={() => act("widen", `${base}/widen`, { config_hash: hash })} loading={busy === "widen"} disabled={!!busy}>Give full approved permissions</Button>
              </div>
            </Card>
          )}
          {agent.status === "active" && can("agent.activate") && (
            <Card>
              <CardHeader title="Pause" description="Stops all work immediately. Resuming re-checks readiness." />
              <div className="space-y-3 px-5 py-4">
                <Field label="Reason (optional)">{(p) => <Input {...p} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
                <Button variant="danger" onClick={() => act("pause", `${base}/pause`, { reason: reason || null })} loading={busy === "pause"} disabled={!!busy}><Pause /> Pause agent</Button>
              </div>
            </Card>
          )}
          {agent.status === "paused" && can("agent.activate") && hash && (
            <Card>
              <CardHeader title="Paused" description={agent.status_reason ?? undefined} />
              <div className="px-5 py-4">
                <Button onClick={() => act("resume", `${base}/resume`, { config_hash: hash })} loading={busy === "resume"} disabled={!!busy}><Play /> Resume</Button>
              </div>
            </Card>
          )}
          {!can("agent.activate") && <Alert tone="info">Only workspace owners can activate, pause or resume agents.</Alert>}
        </div>
      </div>
      <section aria-labelledby="runs-h" className="mt-8">
        <h2 id="runs-h" className="mb-3 text-sm font-semibold">Test runs</h2>
        {!runsQ.data ? <Spinner /> : runsQ.data.length === 0 ? <p className="text-sm text-muted">No runs yet.</p> : (
          <Table label="Test runs">
            <thead><tr><th className={th}>Started</th><th className={th}>Configuration</th><th className={th}>Result</th><th className={th}>Scenarios</th><th className={th}></th></tr></thead>
            <tbody>
              {runsQ.data.map((r) => (
                <tr key={r.id}>
                  <td className={td}><span className="text-xs">{formatDateTime(r.created_at)}</span></td>
                  <td className={td}>v{r.config_version}</td>
                  <td className={td}><RunBadge run={r} /></td>
                  <td className={td}>{r.summary.scenarios ? `${r.summary.passed} / ${r.summary.scenarios}` : "—"}</td>
                  <td className={td}><Link href={`/app/simulations/runs/${r.id}`} className="text-accent underline underline-offset-2">Details</Link></td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </section>
    </>
  );
}
