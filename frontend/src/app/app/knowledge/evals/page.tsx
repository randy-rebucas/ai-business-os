"use client";

import { CheckCircle2, FlaskConical, Play, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { ACCESS_LEVELS } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { AccessLevel, DocumentRow, EvalCase, EvalRun, EvalRunDetail } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const CATEGORIES: [string, string, string][] = [
  ["normal", "Normal question", "answered"],
  ["outdated", "Outdated document", "answered"],
  ["conflicting", "Conflicting policies", "conflicting"],
  ["inaccessible", "Inaccessible document", "insufficient_evidence"],
  ["missing", "Missing information", "insufficient_evidence"],
  ["injection", "Prompt injection in a document", "answered"],
];
const pct = (n: number | null | undefined) => (n == null ? "—" : `${Math.round(n * 100)}%`);
const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

function DocPicker({ label, docs, value, onChange, hint }: {
  label: string; docs: DocumentRow[]; value: string[]; onChange: (v: string[]) => void; hint?: string;
}) {
  return (
    <Field label={label} hint={hint ?? "Hold Ctrl / Cmd to select several."}>
      {(p) => (
        <Select {...p} multiple className="h-28" value={value}
          onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
          {docs.map((d) => <option key={d.id} value={d.id}>{d.title} ({d.status.replace("_", " ")})</option>)}
        </Select>
      )}
    </Field>
  );
}

function CaseForm({ docs, onCreated }: { docs: DocumentRow[]; onCreated: () => void }) {
  const { can } = useSession();
  const [question, setQuestion] = useState("");
  const [category, setCategory] = useState("normal");
  const [expectedStatus, setExpectedStatus] = useState("answered");
  const [contains, setContains] = useState("");
  const [forbiddenPhrases, setForbiddenPhrases] = useState("");
  const [expectedDocs, setExpectedDocs] = useState<string[]>([]);
  const [forbiddenDocs, setForbiddenDocs] = useState<string[]>([]);
  const [levels, setLevels] = useState<AccessLevel[]>(["general"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/v1/knowledge/evals/cases", {
        method: "POST", org: true, body: {
          question, category, expected_status: expectedStatus, expected_answer_contains: list(contains),
          forbidden_phrases: list(forbiddenPhrases), expected_document_ids: expectedDocs,
          forbidden_document_ids: forbiddenDocs, access_levels: levels,
        },
      });
      setQuestion(""); setContains(""); setForbiddenPhrases(""); setExpectedDocs([]); setForbiddenDocs([]);
      onCreated();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader title="Add a test question" description="Each case states what a correct, safe answer looks like. Grading is deterministic — no AI judge." />
      <form onSubmit={submit} className="space-y-4 px-5 py-4">
        <Field label="Question">{(p) => <Textarea {...p} rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} />}</Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Scenario">
            {(p) => <Select {...p} value={category} onChange={(e) => {
              setCategory(e.target.value);
              setExpectedStatus(CATEGORIES.find(([k]) => k === e.target.value)?.[2] ?? "answered");
            }}>{CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}
          </Field>
          <Field label="Expected outcome">
            {(p) => <Select {...p} value={expectedStatus} onChange={(e) => setExpectedStatus(e.target.value)}>
              <option value="answered">Answered from sources</option>
              <option value="insufficient_evidence">Says the information is missing</option>
              <option value="conflicting">Reports the conflict</option>
            </Select>}
          </Field>
          <Field label="Answer must contain (optional)" hint="Comma-separated, e.g. Finance Manager, 5,000">
            {(p) => <Input {...p} value={contains} onChange={(e) => setContains(e.target.value)} />}
          </Field>
          <Field label="Answer must never contain (optional)" hint="Comma-separated, e.g. a phrase planted in a document">
            {(p) => <Input {...p} value={forbiddenPhrases} onChange={(e) => setForbiddenPhrases(e.target.value)} />}
          </Field>
          <DocPicker label="Expected source documents (optional)" docs={docs} value={expectedDocs} onChange={setExpectedDocs} />
          <DocPicker label="Documents that must NOT be retrieved (optional)" docs={docs} value={forbiddenDocs} onChange={setForbiddenDocs}
            hint="Outdated or above the tested access level. Retrieving one fails the case as a security failure." />
        </div>
        <fieldset>
          <legend className="text-sm font-medium">Ask with the access of</legend>
          <div className="mt-2 flex flex-wrap gap-4">
            {ACCESS_LEVELS.filter(([l]) => l === "general" || (l === "restricted" ? can("knowledge.review") : can("knowledge.confidential"))).map(([l, label]) => (
              <Checkbox key={l} label={label} checked={levels.includes(l)} disabled={l === "general"}
                onChange={(e) => setLevels((xs) => (e.target.checked ? [...xs, l] : xs.filter((x) => x !== l)))} />
            ))}
          </div>
        </fieldset>
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" loading={busy} disabled={question.trim().length < 3}>Add case</Button>
      </form>
    </Card>
  );
}

function RunDetail({ runId }: { runId: string }) {
  const { data, error } = useOrgData<EvalRunDetail>(`/api/v1/knowledge/evals/runs/${runId}`);
  if (error) return <ErrorState error={error} />;
  if (!data) return <Spinner />;
  return (
    <ul className="divide-y divide-border">
      {data.results.map((r) => (
        <li key={r.id} className="px-5 py-3">
          <div className="flex items-start gap-3">
            {r.passed ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-label="Passed" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-label="Failed" />}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{r.question}</p>
              <p className="text-xs text-muted">{r.category} · got “{r.status.replaceAll("_", " ")}” · reciprocal rank {Number(r.reciprocal_rank).toFixed(2)}</p>
              <p className="mt-1 line-clamp-2 text-xs text-fg/80">{r.answer}</p>
              {r.failure_reasons.length > 0 && <ul className="mt-1 list-disc pl-4 text-xs text-danger">{r.failure_reasons.map((f) => <li key={f}>{f}</li>)}</ul>}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function EvalsPage() {
  const { orgId } = useSession();
  const { mutate } = useSWRConfig();
  const cases = useOrgData<EvalCase[]>("/api/v1/knowledge/evals/cases");
  const runs = useOrgData<EvalRun[]>("/api/v1/knowledge/evals/runs");
  const docs = useOrgData<DocumentRow[]>("/api/v1/documents");
  const [mode, setMode] = useState("hybrid");
  const [topK, setTopK] = useState(5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const titles = new Map((docs.data ?? []).map((d) => [d.id, d.title]));

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api<EvalRun>("/api/v1/knowledge/evals/runs", { method: "POST", org: true, body: { mode, top_k: topK } });
      await mutate(["/api/v1/knowledge/evals/runs", orgId]);
      setOpen(r.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const remove = async (id: string) => {
    await api(`/api/v1/knowledge/evals/cases/${id}`, { method: "DELETE", org: true });
    await mutate(["/api/v1/knowledge/evals/cases", orgId]);
  };

  return (
    <>
      <PageHeader eyebrow="Knowledge" title="Knowledge evaluation"
        description="Test whether answers find the right documents, cite them correctly, admit gaps, and never leak documents or follow instructions planted in them." />
      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-6">
          {docs.data && <CaseForm docs={docs.data} onCreated={() => mutate(["/api/v1/knowledge/evals/cases", orgId])} />}
          <Card>
            <CardHeader title={`Test cases (${cases.data?.length ?? 0})`} />
            {cases.error ? <ErrorState error={cases.error} /> : !cases.data ? <Spinner /> : cases.data.length === 0 ? (
              <p className="px-5 py-4 text-sm text-muted">No cases yet.</p>
            ) : (
              <ul className="divide-y divide-border">
                {cases.data.map((c) => (
                  <li key={c.id} className="flex items-start justify-between gap-3 px-5 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{c.question}</p>
                      <p className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted">
                        <span>{CATEGORIES.find(([k]) => k === c.category)?.[1]}</span>
                        <span>expects {c.expected_status.replaceAll("_", " ")}</span>
                        {c.expected_document_ids.length > 0 && <span>sources: {c.expected_document_ids.map((d) => titles.get(d) ?? "deleted").join(", ")}</span>}
                        {c.forbidden_document_ids.length > 0 && <span className="text-danger">must not retrieve: {c.forbidden_document_ids.map((d) => titles.get(d) ?? "hidden document").join(", ")}</span>}
                      </p>
                    </div>
                    <Button variant="ghost" size="icon" aria-label="Delete case" onClick={() => remove(c.id)}><Trash2 /></Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Run the suite" description="Compare retrieval settings by running the same cases with each." />
            <div className="flex flex-wrap items-end gap-3 px-5 py-4">
              <Field label="Retrieval">
                {(p) => <Select {...p} value={mode} onChange={(e) => setMode(e.target.value)} className="w-40">
                  <option value="hybrid">Hybrid</option><option value="vector">Vector only</option><option value="keyword">Keyword only</option>
                </Select>}
              </Field>
              <Field label="Top K">{(p) => <Input {...p} type="number" min={1} max={20} className="w-24" value={topK} onChange={(e) => setTopK(Number(e.target.value))} />}</Field>
              <Button onClick={run} loading={busy} disabled={!cases.data?.length}><Play /> Run {cases.data?.length ?? 0} cases</Button>
            </div>
            {error && <div className="px-5 pb-4"><Alert tone="danger">{error}</Alert></div>}
          </Card>
          {runs.data && runs.data.length === 0 && <EmptyState icon={FlaskConical} title="No runs yet" />}
          {runs.data && runs.data.length > 0 && (
            <Table label="Evaluation runs">
              <thead>
                <tr><th className={th}>Run</th><th className={th}>Pass</th><th className={th}>Hit / MRR</th><th className={th}>Citations</th><th className={th}>Security</th></tr>
              </thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.id} className="cursor-pointer hover:bg-surface/60" onClick={() => setOpen(open === r.id ? null : r.id)}>
                    <td className={td}>
                      <button type="button" className="text-left font-medium underline-offset-2 hover:underline" aria-expanded={open === r.id}>
                        {r.config.mode}, top {r.config.top_k}
                      </button>
                      <p className="text-xs text-muted">{formatDateTime(r.created_at)} · {r.config.llm_provider}/{r.config.embedding_provider}</p>
                    </td>
                    <td className={`${td} tabular-nums`}>{r.passed_count}/{r.case_count}</td>
                    <td className={`${td} tabular-nums`}>{pct(r.metrics.hit_rate)} / {r.metrics.mrr?.toFixed(2) ?? "—"}</td>
                    <td className={`${td} tabular-nums`}>{pct(r.metrics.citation_validity)}</td>
                    <td className={td}>{r.metrics.security_failures ? <Badge tone="danger">{r.metrics.security_failures} failed</Badge> : <Badge tone="success">OK</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          {open && <Card><CardHeader title="Run results" /><RunDetail runId={open} /></Card>}
        </div>
      </div>
    </>
  );
}
