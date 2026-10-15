"use client";

import Link from "next/link";

import { Badge, Table, td, th } from "@/components/ui/display";
import { ACTIVE_RUN, EXEC_STATUS, RUN_STATUS } from "@/lib/labels";
import type { EvidenceRef, ToolExecution, WorkflowRun } from "@/lib/types";

export const isActive = (run?: Pick<WorkflowRun, "status">) => !!run && ACTIVE_RUN.includes(run.status);

export function RunStatusBadge({ status }: { status: string }) {
  const s = RUN_STATUS[status] ?? { label: status, tone: "neutral" as const };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function ExecStatusBadge({ status }: { status: string }) {
  const s = EXEC_STATUS[status] ?? { label: status, tone: "neutral" as const };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

function json(v: unknown): string {
  return typeof v === "string" ? v : JSON.stringify(v, null, 2);
}

function evidenceHref(e: EvidenceRef): string | null {
  if (e.type === "workflow_run") return `/app/tasks/${e.id}`;
  if (e.type === "invoice" || e.type === "expense" || e.type === "draft") return "/app/records";
  return null;
}

export function EvidenceList({ items }: { items: EvidenceRef[] }) {
  if (!items.length) return null;
  return (
    <ul className="mt-1 flex flex-wrap gap-1.5">
      {items.slice(0, 12).map((e) => {
        const href = evidenceHref(e);
        return (
          <li key={`${e.type}-${e.id}`} className="rounded-sm border border-border bg-surface px-1.5 py-0.5 text-xs">
            {href ? <Link href={href} className="text-accent underline underline-offset-2">{e.label}</Link> : e.label}
          </li>
        );
      })}
      {items.length > 12 && <li className="text-xs text-muted">+{items.length - 12} more</li>}
    </ul>
  );
}

/** The evidence ledger for one run: every attempted call, what governance decided and what happened. */
export function ExecutionTable({ rows, label }: { rows: ToolExecution[]; label: string }) {
  return (
    <Table label={label}>
      <thead><tr><th className={th}>Step</th><th className={th}>Tool</th><th className={th}>Outcome</th><th className={th}>Why · evidence</th></tr></thead>
      <tbody>
        {rows.map((x) => (
          <tr key={x.id}>
            <td className={td}>{x.step_no}</td>
            <td className={td}>
              <span className="ident text-xs">{x.tool}</span>
              <div className="text-xs text-subtle">{x.scope ?? "always allowed"} · {x.risk} risk</div>
            </td>
            <td className={td}>
              <ExecStatusBadge status={x.status} />
              {x.attempts > 1 && <div className="text-xs text-muted">{x.attempts} attempts</div>}
              {x.duration_ms != null && <div className="text-xs text-subtle">{x.duration_ms} ms</div>}
            </td>
            <td className={td}>
              <span className="text-xs">{x.reason}</span>
              {x.error && <div className="text-xs text-danger">{x.error}</div>}
              <EvidenceList items={x.evidence} />
              <details className="mt-1">
                <summary className="cursor-pointer text-xs text-muted">Input and output</summary>
                <pre className="mt-1 max-h-64 overflow-auto rounded-md bg-surface p-2 text-xs">{`input ${json(x.input)}\n\noutput ${json(x.output)}`}</pre>
                <p className="ident mt-1 text-[11px] text-subtle">input {x.input_hash.slice(0, 12)} · {x.registry_version}{x.idempotency_key ? ` · key ${x.idempotency_key.slice(0, 12)}` : ""}</p>
              </details>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
