"use client";

import { Check, Wrench, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, Table, td, th } from "@/components/ui/display";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { DECISION, DIMENSION_LABEL, SCENARIO_CATEGORY } from "@/lib/labels";
import type { SimulationResult, SimulationRun } from "@/lib/types";

export function RunBadge({ run }: { run: Pick<SimulationRun, "status" | "passed"> }) {
  if (run.status === "queued" || run.status === "running") return <Badge tone="info">{run.status === "queued" ? "Queued" : "Running"}</Badge>;
  if (run.status === "error") return <Badge tone="danger">Error</Badge>;
  return run.passed ? <Badge tone="success">Passed</Badge> : <Badge tone="danger">Failed</Badge>;
}

export const isRunning = (run?: { status: string }) => !!run && (run.status === "queued" || run.status === "running");

export function ScoresTable({ run }: { run: SimulationRun }) {
  const keys = Object.keys(DIMENSION_LABEL).filter((k) => run.scores[k]);
  return (
    <Table label="Scores by dimension">
      <thead><tr><th className={th}>Dimension</th><th className={th}>Checks passed</th><th className={th}>Score</th><th className={th}>Required</th></tr></thead>
      <tbody>
        {keys.map((k) => {
          const s = run.scores[k];
          const need = run.thresholds[k];
          const below = s.score != null && need != null && s.score < need;
          return (
            <tr key={k}>
              <td className={td}>{DIMENSION_LABEL[k]}</td>
              <td className={td}>{s.total ? `${s.passed} / ${s.total}` : "—"}</td>
              <td className={td}>{s.score == null ? <span className="text-subtle">Not tested</span>
                : <Badge tone={below ? "danger" : "success"}>{Math.round(s.score * 100)}%</Badge>}</td>
              <td className={td}>{need != null ? `${Math.round(need * 100)}%` : "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

function short(v: unknown): string {
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length > 140 ? `${s.slice(0, 140)}…` : s;
}

export function ResultCard({ result, canApply, onApplied }: { result: SimulationResult; canApply: boolean; onApplied: () => void }) {
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<string | null>(null);
  const apply = async (i: number) => {
    setBusy(i);
    setError(null);
    try {
      const cfg = await api<{ version: number }>(`/api/v1/simulations/results/${result.id}/suggestions/${i}/apply`, { method: "POST", org: true });
      setApplied(`Applied as configuration version ${cfg.version} (draft). Submit it for approval, then re-run the tests.`);
      onApplied();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };
  return (
    <Card className="px-5 py-4">
      <details open={!result.passed}>
        <summary className="flex cursor-pointer flex-wrap items-center gap-2">
          {result.passed ? <Badge tone="success">Passed</Badge> : <Badge tone="danger">Failed</Badge>}
          {result.mandatory_failed && <Badge tone="danger">Security check failed</Badge>}
          <span className="font-medium text-fg">{result.title}</span>
          <span className="text-xs text-muted">{SCENARIO_CATEGORY[result.category] ?? result.category} · outcome: {result.outcome}</span>
        </summary>
        <div className="mt-4 space-y-4">
          <ul className="space-y-1 text-sm">
            {result.assertions.map((a, i) => (
              <li key={i} className="flex gap-2">
                {a.passed ? <Check aria-label="Passed" className="mt-0.5 size-4 shrink-0 text-success" /> : <X aria-label="Failed" className="mt-0.5 size-4 shrink-0 text-danger" />}
                <span>
                  {a.label}{a.mandatory && <span className="text-xs text-muted"> (mandatory)</span>}
                  <span className="block text-xs text-muted">{DIMENSION_LABEL[a.dimension]} — {a.detail}</span>
                </span>
              </li>
            ))}
          </ul>
          {result.output.status !== "none" && (
            <div className="rounded-md bg-surface px-3 py-2 text-sm">
              <p className="text-xs font-medium uppercase tracking-wide text-subtle">Answer ({result.output.status.replaceAll("_", " ")}, {result.output.valid_citations} verified citation{result.output.valid_citations === 1 ? "" : "s"})</p>
              <p className="mt-1 whitespace-pre-line">{result.output.answer || "—"}</p>
              {result.output.redactions > 0 && <p className="mt-1 text-xs text-warning">Planted instructions removed from {result.output.redactions} source(s) before planning.</p>}
            </div>
          )}
          <Table label={`Actions in ${result.title}`}>
            <thead><tr><th className={th}>#</th><th className={th}>Tool</th><th className={th}>Decision</th><th className={th}>Why</th></tr></thead>
            <tbody>
              {result.trace.map((s) => (
                <tr key={`${s.n}-${s.trigger}`}>
                  <td className={td}>{s.n}</td>
                  <td className={td}><span className="ident text-xs">{s.tool}</span><div className="text-xs text-subtle">{short(s.input)}</div></td>
                  <td className={td}><Badge tone={DECISION[s.decision]?.tone ?? "neutral"}>{DECISION[s.decision]?.label ?? s.decision}</Badge>
                    {s.attempts && s.attempts > 1 && <div className="text-xs text-muted">{s.attempts} attempts</div>}</td>
                  <td className={td}><span className="text-xs">{s.reason}</span>
                    {Array.isArray(s.result?.validated_checks) && <div className="text-xs text-warning">{(s.result.validated_checks as string[]).join("; ")}</div>}</td>
                </tr>
              ))}
            </tbody>
          </Table>
          {!result.passed && result.analysis.explanation && (
            <Alert tone="warning" title="What failed">
              <p>{result.analysis.explanation}</p>
              {!!result.analysis.suggestions?.length && (
                <ul className="mt-2 space-y-2">
                  {result.analysis.suggestions.map((s, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-2">
                      <span>{s.text}</span>
                      {s.applicable && canApply && (
                        <Button size="sm" variant="secondary" loading={busy === i} disabled={busy !== null || !!applied} onClick={() => apply(i)}><Wrench /> Apply</Button>
                      )}
                      {!s.applicable && <span className="text-xs text-muted">(change it yourself in the configuration)</span>}
                    </li>
                  ))}
                </ul>
              )}
            </Alert>
          )}
          {applied && <Alert tone="success">{applied}</Alert>}
          {error && <Alert tone="danger">{error}</Alert>}
        </div>
      </details>
    </Card>
  );
}
