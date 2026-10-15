"use client";

import { Check, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { ACTION_STATUS, RISK_TONE } from "@/lib/labels";
import type { ActionRequest } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const LABELS: Record<string, string> = {
  recipient: "To", subject: "Subject", body: "Message", invoice_number: "Invoice", balance: "Balance", currency: "Currency",
};

/** A held agent action: shows exactly what would happen. The decision carries the hash of what was shown. */
export function ActionCard({ req, canDecide, onDecided }: { req: ActionRequest; canDecide: boolean; onDecided: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const status = ACTION_STATUS[req.status] ?? { label: req.status, tone: "neutral" as const };
  const decide = async (decision: "approved" | "rejected") => {
    setBusy(decision);
    setError(null);
    try {
      await api(`/api/v1/approvals/actions/${req.id}/decide`, { method: "POST", org: true,
        body: { decision, note: note || null, params_hash: req.params_hash } });
      onDecided();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };
  const order = Object.keys(LABELS);
  const rank = (k: string) => (order.includes(k) ? order.indexOf(k) : order.length);
  const params = Object.entries(req.parameters).filter(([k]) => k !== "draft_id").sort(([a], [b]) => rank(a) - rank(b));
  return (
    <Card className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={status.tone}>{status.label}</Badge>
        <Badge tone={RISK_TONE[req.risk] ?? "neutral"}>{req.risk} risk</Badge>
        <span className="font-medium text-fg">{req.tool_label}</span>
        <span className="text-xs text-muted">
          {req.agent_name} · <Link href={`/app/tasks/${req.run_id}`} className="text-accent underline underline-offset-2">{req.task_title}</Link> · {formatDateTime(req.created_at)}
        </span>
      </div>
      <p className="mt-2 text-sm text-muted">Held because: {req.reason}</p>
      <dl className="mt-3 space-y-2 rounded-md bg-surface px-3 py-2 text-sm">
        {params.map(([k, v]) => (
          <div key={k} className="grid gap-1 sm:grid-cols-[7rem_1fr]">
            <dt className="text-muted">{LABELS[k] ?? k.replaceAll("_", " ")}</dt>
            <dd className="whitespace-pre-line text-fg">{typeof v === "string" ? v : JSON.stringify(v)}</dd>
          </div>
        ))}
      </dl>
      <p className="ident mt-2 text-[11px] text-subtle">bound to {req.params_hash.slice(0, 16)} · {req.policy_version}</p>
      {req.status === "pending" && canDecide && (
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Field label="Note (required to reject)" className="min-w-64 flex-1">{(p) => <Input {...p} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
          <Button onClick={() => decide("approved")} loading={busy === "approved"} disabled={!!busy}><Check /> Approve this exact action</Button>
          <Button variant="secondary" onClick={() => decide("rejected")} loading={busy === "rejected"} disabled={!!busy}><X /> Reject</Button>
        </div>
      )}
      {req.status === "pending" && !canDecide && <p className="mt-3 text-xs text-muted">Only workspace owners can decide on agent actions.</p>}
      {req.decided_by_name && <p className="mt-2 text-xs text-muted">Decided by {req.decided_by_name} ({req.decided_by_role}) {formatDateTime(req.decided_at)}{req.note && ` — “${req.note}”`}</p>}
      {error && <Alert tone="danger" className="mt-3">{error}</Alert>}
    </Card>
  );
}
