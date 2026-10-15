"use client";

import { MessagesSquare, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, EmptyState, ErrorState, PageHeader, Spinner } from "@/components/ui/display";
import { Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { InterviewQuestion } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const PATH = "/api/v1/interview";

function QuestionCard({ q, canWrite, onChange }: { q: InterviewQuestion; canWrite: boolean; onChange: () => void }) {
  const [answer, setAnswer] = useState(q.answer ?? "");
  const [editing, setEditing] = useState(q.status === "open");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = async (path: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    try {
      await api(`${PATH}/${q.id}/${path}`, { method: "POST", org: true, body });
      setEditing(false);
      onChange();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-medium text-fg">{q.question}</p>
        <div className="flex gap-2">
          {q.source === "model" && <Badge tone="info">Suggested by AI</Badge>}
          {q.status === "answered" && <Badge tone="success">Answered</Badge>}
        </div>
      </div>
      {q.rationale && <p className="mt-1 text-xs text-muted">Why we ask: {q.rationale}</p>}
      {editing && canWrite ? (
        <form className="mt-3 space-y-2" onSubmit={(e) => { e.preventDefault(); void act("answer", { answer }); }}>
          <label htmlFor={`a-${q.id}`} className="sr-only">Your answer</label>
          <Textarea id={`a-${q.id}`} rows={3} value={answer} onChange={(e) => setAnswer(e.target.value)} />
          <div className="flex gap-2">
            <Button type="submit" size="sm" loading={busy} disabled={!answer.trim()}>Save answer</Button>
            {q.status === "open" ? (
              <Button variant="ghost" size="sm" onClick={() => act("dismiss")} disabled={busy}>Not relevant</Button>
            ) : (
              <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
            )}
          </div>
        </form>
      ) : q.answer ? (
        <div className="mt-3 rounded-md bg-surface px-3 py-2 text-sm">
          <p className="whitespace-pre-line">{q.answer}</p>
          <p className="mt-1 text-xs text-subtle">
            {q.answered_at && formatDateTime(q.answered_at)}
            {canWrite && <button type="button" className="ml-3 underline" onClick={() => setEditing(true)}>Edit</button>}
          </p>
        </div>
      ) : null}
      {error && <Alert tone="danger" className="mt-2">{error}</Alert>}
    </Card>
  );
}

export default function InterviewPage() {
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const { data, error } = useOrgData<InterviewQuestion[]>(PATH);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [genError, setGenError] = useState<string | null>(null);
  const refresh = () => mutate([PATH, orgId]);
  const generate = async () => {
    setBusy(true);
    setGenError(null);
    try {
      const r = await api<{ created: number; label: string | null }>(`${PATH}/generate`, { method: "POST", org: true });
      setNote(r.created ? `${r.created} new question${r.created > 1 ? "s" : ""}.` : "No new questions — you're up to date.");
      if (r.label) setNote((n) => `${n} Tailored AI questions need a connected AI model; these come from your profile gaps.`);
      await refresh();
    } catch (err) {
      setGenError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const open = data?.filter((q) => q.status === "open") ?? [];
  const answered = data?.filter((q) => q.status === "answered") ?? [];
  const canWrite = can("company.write");

  return (
    <>
      <PageHeader title="Business interview"
        description="Follow-up questions about how your business really works — approval limits, exceptions, unwritten rules. Your answers shape how AI employees are configured."
        actions={canWrite && <Button onClick={generate} loading={busy}><RefreshCw /> Find new questions</Button>} />
      {note && <Alert tone="info" className="mb-4">{note}</Alert>}
      {genError && <Alert tone="danger" className="mb-4">{genError}</Alert>}
      {error ? <ErrorState error={error} /> : !data ? <Spinner /> : data.length === 0 ? (
        <EmptyState icon={MessagesSquare} title="No questions yet"
          action={canWrite && <Button onClick={generate} loading={busy}>Start the interview</Button>}>
          We&apos;ll look at your company profile and documents and ask about what&apos;s missing.
        </EmptyState>
      ) : (
        <div className="space-y-8">
          <section aria-labelledby="open-q">
            <h2 id="open-q" className="mb-3 text-sm font-semibold">Open questions ({open.length})</h2>
            {open.length === 0 ? <p className="text-sm text-muted">All caught up.</p> : (
              <div className="space-y-3">{open.map((q) => <QuestionCard key={q.id} q={q} canWrite={canWrite} onChange={refresh} />)}</div>
            )}
          </section>
          {answered.length > 0 && (
            <section aria-labelledby="answered-q">
              <h2 id="answered-q" className="mb-3 text-sm font-semibold">Answered ({answered.length})</h2>
              <div className="space-y-3">{answered.map((q) => <QuestionCard key={`${q.id}-${q.answered_at}`} q={q} canWrite={canWrite} onChange={refresh} />)}</div>
            </section>
          )}
        </div>
      )}
    </>
  );
}
