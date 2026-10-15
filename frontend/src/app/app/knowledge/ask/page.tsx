"use client";

import { Info, Quote, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, EmptyState, PageHeader } from "@/components/ui/display";
import { Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { ANSWER_STATUS } from "@/lib/labels";
import type { AiStatus, Answer } from "@/lib/types";

function AnswerCard({ a }: { a: Answer }) {
  const st = ANSWER_STATUS[a.status];
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <p className="font-medium text-fg">{a.question}</p>
        <Badge tone={st.tone}>{st.label}</Badge>
      </div>
      <div className="space-y-4 px-5 py-4">
        {a.status === "unsupported" && (
          <Alert tone="danger" title="This answer failed verification">
            {a.checks.downgraded_reasons.join("; ")}. It is shown for transparency only.
          </Alert>
        )}
        <p className="whitespace-pre-line text-[15px] leading-relaxed">{a.answer}</p>
        {a.conflicts.length > 0 && (
          <Alert tone="warning" title="Conflicting sources">
            <ul className="list-disc pl-4">{a.conflicts.map((c) => <li key={c}>{c}</li>)}</ul>
            Ask the document owner which one is current, then archive or supersede the outdated one.
          </Alert>
        )}
        {a.follow_up_question && <p className="text-sm text-muted"><Info className="mr-1 inline size-4" aria-hidden />{a.follow_up_question}</p>}
        {a.citations.length > 0 && (
          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-subtle">Sources cited</h3>
            <ol className="space-y-2">
              {a.citations.map((c, i) => (
                <li key={`${c.chunk_id}-${i}`} className="rounded-md border border-border bg-surface/50 px-4 py-3">
                  <blockquote className="flex gap-2 text-sm"><Quote className="mt-0.5 size-4 shrink-0 text-subtle" aria-hidden />{c.quote}</blockquote>
                  <p className="mt-2 text-xs text-muted">
                    <Link href={`/app/knowledge/${c.document_id}`} className="font-medium text-accent underline-offset-2 hover:underline">{c.document_title}</Link>
                    {c.section && ` · ${c.section}`}{c.page_number && ` · page ${c.page_number}`} · v{c.version_no}
                  </p>
                </li>
              ))}
            </ol>
          </div>
        )}
        <details className="text-sm">
          <summary className="cursor-pointer text-muted">How this answer was checked ({a.sources.length} source{a.sources.length === 1 ? "" : "s"} retrieved)</summary>
          <ul className="mt-2 space-y-1 text-muted">
            <li>Valid citations: {a.checks.valid_citations}</li>
            <li>Rejected citations: {a.checks.invalid_citations.length ? a.checks.invalid_citations.map((x) => `${x.source} (${x.reason})`).join(", ") : "none"}</li>
            <li>Figures not found in sources: {a.checks.unsupported_numbers.length ? a.checks.unsupported_numbers.join(", ") : "none"}</li>
          </ul>
          <ol className="mt-3 space-y-2">
            {a.sources.map((s, i) => (
              <li key={s.chunk_id} className="rounded-md border border-border px-3 py-2">
                <p className="text-xs text-muted">
                  S{i + 1} · {s.document_title}{s.section && ` · ${s.section}`} · keyword rank {s.keyword_rank ?? "—"} · vector {s.vector_score?.toFixed(2) ?? "—"}
                </p>
                <p className="mt-1 line-clamp-3 text-xs">{s.content}</p>
              </li>
            ))}
          </ol>
        </details>
        <p className="text-xs text-subtle">{a.label ?? `Answered by ${a.model}`}</p>
      </div>
    </Card>
  );
}

export default function AskPage() {
  const { data: status } = useOrgData<AiStatus>("/api/v1/knowledge/status");
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Answer[]>([]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (question.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      const a = await api<Answer>("/api/v1/knowledge/ask", { method: "POST", org: true, body: { question } });
      setAnswers((xs) => [a, ...xs]);
      setQuestion("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader eyebrow="Knowledge" title="Ask the knowledge base"
        description="Answers come only from approved company documents, with the exact passages they rely on. If the documents don't cover it, you'll be told." />
      {status?.llm.dev_adapter && (
        <Alert tone="info" className="mb-4" title="Development mode">
          No AI model is connected. Answers quote the best-matching sentence from your documents so you can test retrieval and citations.
        </Alert>
      )}
      <form onSubmit={submit} className="mb-6 space-y-3">
        <label htmlFor="question" className="sr-only">Your question</label>
        <Textarea id="question" rows={3} placeholder="e.g. Who must approve a refund above our automatic limit?" value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit(e); }} />
        <div className="flex items-center gap-3">
          <Button type="submit" loading={busy} disabled={question.trim().length < 3}><Sparkles /> Ask</Button>
          <span className="text-xs text-subtle">Ctrl + Enter to send</span>
        </div>
        {error && <Alert tone="danger">{error}</Alert>}
      </form>
      {answers.length === 0 ? (
        <EmptyState icon={Sparkles} title="Ask about your policies, prices or procedures">
          Only documents that are indexed (reviewed and approved) are searched, filtered to what you&apos;re allowed to see.
        </EmptyState>
      ) : (
        <div className="space-y-6">{answers.map((a) => <AnswerCard key={a.id} a={a} />)}</div>
      )}
      <Card className="mt-8">
        <CardHeader title="Tip" description="Wrong or missing answer? Fix the source: upload the right document, approve it, and supersede the outdated one." />
      </Card>
    </>
  );
}
