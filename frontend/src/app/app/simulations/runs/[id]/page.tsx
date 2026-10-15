"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useSWRConfig } from "swr";

import { isRunning, ResultCard, RunBadge, ScoresTable } from "@/components/simulation/shared";
import { Alert, Card, CardHeader, ErrorState, Meta, PageHeader, ProgressBar, Spinner } from "@/components/ui/display";
import { pollWhile, useOrgData } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { SimulationRunDetail } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const path = `/api/v1/simulations/runs/${id}`;
  const { data: run, error } = useOrgData<SimulationRunDetail>(path, pollWhile<SimulationRunDetail>((r) => isRunning(r), 1500));
  if (error) return <ErrorState error={error} />;
  if (!run) return <Spinner />;
  const total = run.suite.length || 1;
  const failed = run.results.filter((r) => !r.passed);
  return (
    <>
      <Link href={`/app/agents/${run.instance_id}/readiness`} className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-fg"><ArrowLeft className="size-4" /> Readiness & deployment</Link>
      <PageHeader title={`${run.agent_name ?? "Agent"} — configuration v${run.config_version}`}
        description="Every scenario ran in a sandbox: no real system or customer was contacted." actions={<RunBadge run={run} />} />
      {isRunning(run) ? (
        <Card className="mb-6 px-5 py-4">
          <p className="mb-2 text-sm">{run.progress.length} of {total} scenarios done…</p>
          <ProgressBar value={Math.round((100 * run.progress.length) / total)} label="Simulation progress" />
        </Card>
      ) : run.status === "error" ? <Alert tone="danger" title="The run failed">{run.error}</Alert> : (
        <div className="space-y-6">
          {run.planner.label && <Alert tone="warning" title="Development mode">{run.planner.label}</Alert>}
          {run.passed ? (
            <Alert tone="success" title="All required checks passed">Every mandatory security and authorisation check passed and every score met this agent&apos;s threshold.</Alert>
          ) : (
            <Alert tone="danger" title="Not ready">
              <ul className="list-disc pl-4">{run.summary.gate_reasons?.map((r) => <li key={r}>{r}</li>)}</ul>
            </Alert>
          )}
          <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
            <ScoresTable run={run} />
            <Card className="self-start">
              <CardHeader title="Run" />
              <dl className="px-5 py-3">
                <Meta label="Scenarios">{`${run.summary.passed} of ${run.summary.scenarios} passed`}</Meta>
                <Meta label="Security failures">{run.summary.mandatory_failures}</Meta>
                <Meta label="Planner">{run.planner.mode === "model" ? `${run.planner.provider} · ${run.planner.model}` : "Scripted attempts"}</Meta>
                <Meta label="Finished">{formatDateTime(run.finished_at)}</Meta>
                <Meta label="Fingerprint" mono>{run.config_hash.slice(0, 12)}</Meta>
              </dl>
            </Card>
          </div>
          <section aria-labelledby="results-h" className="space-y-3">
            <h2 id="results-h" className="text-sm font-semibold">Scenarios ({failed.length} failed)</h2>
            {run.results.map((r) => (
              <ResultCard key={r.id} result={r} canApply={can("agent.configure")}
                onApplied={() => mutate([`/api/v1/agents/${run.instance_id}`, orgId])} />
            ))}
          </section>
        </div>
      )}
    </>
  );
}
