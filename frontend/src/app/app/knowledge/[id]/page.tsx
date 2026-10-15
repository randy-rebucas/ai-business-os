"use client";

import { AlertTriangle, ArrowLeft, Check, Download, RefreshCw, Upload } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";
import { useSWRConfig } from "swr";

import { AccessBadge, formatBytes, isBusy, StatusBadge } from "@/components/knowledge/shared";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, ErrorState, Meta, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { errorMessage } from "@/lib/forms";
import { pollWhile, useOrgData } from "@/lib/hooks";
import { ACCESS_LEVELS, DOC_TYPE_LABEL, DOC_TYPES, PIPELINE_STEPS } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { Chunk, DocumentDetail, DocumentRow } from "@/lib/types";
import { uploadWithProgress } from "@/lib/upload";
import { cn, formatDate, formatDateTime } from "@/lib/utils";

function Progress({ doc }: { doc: DocumentDetail }) {
  const done = new Set(doc.latest_job?.steps.map((s) => s.step));
  const steps = PIPELINE_STEPS.filter(([k]) => k !== "fetched" || doc.source_type === "url");
  return (
    <Card className="mb-6">
      <CardHeader title="Processing" description={doc.latest_job && doc.latest_job.attempts > 1 ? `Attempt ${doc.latest_job.attempts} of ${doc.latest_job.max_attempts}` : "This page updates automatically."} />
      <ol className="flex flex-wrap gap-x-6 gap-y-2 px-5 py-4 text-sm">
        {steps.map(([k, label]) => (
          <li key={k} className={cn("flex items-center gap-2", done.has(k) ? "text-fg" : "text-subtle")}>
            {done.has(k) ? <Check className="size-4 text-success" aria-hidden /> :
              <span aria-hidden className="size-3 rounded-full border-2 border-current" />}
            {label}
          </li>
        ))}
      </ol>
      {doc.error_message && <p className="px-5 pb-4 text-xs text-warning">{doc.error_message}</p>}
    </Card>
  );
}

function ReviewPanel({ doc, onDone }: { doc: DocumentDetail; onDone: () => void }) {
  const { can } = useSession();
  const { data: others } = useOrgData<DocumentRow[]>("/api/v1/documents?status=indexed");
  const [docType, setDocType] = useState(doc.doc_type);
  const [access, setAccess] = useState(doc.access_level);
  const [effective, setEffective] = useState(doc.effective_date ?? "");
  const [supersedes, setSupersedes] = useState(doc.supersedes_document_id ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const decide = async (decision: "approve" | "reject") => {
    setBusy(decision);
    setError(null);
    try {
      if ((supersedes || null) !== doc.supersedes_document_id) {
        await api(`/api/v1/documents/${doc.id}`, { method: "PATCH", org: true, body: { supersedes_document_id: supersedes || null } });
      }
      await api(`/api/v1/documents/${doc.id}/review`, {
        method: "POST", org: true,
        body: { decision, note: note.trim() || null, doc_type: docType, access_level: access, effective_date: effective || null },
      });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className="mb-6 border-warning/40">
      <CardHeader title="Review before AI employees can use this"
        description="Check that the extracted summary and sections match the original, then approve. Rejected documents are archived." />
      <div className="space-y-5 px-5 py-4">
        <div>
          <h3 className="text-xs font-medium uppercase tracking-wide text-subtle">Extracted summary</h3>
          <p className="mt-1 whitespace-pre-line text-sm">{doc.summary ?? "No summary available."}</p>
          {doc.summary_label && <p className="mt-1 text-xs text-subtle">{doc.summary_label}</p>}
        </div>
        {doc.warnings.length > 0 && (
          <ul className="space-y-2">
            {doc.warnings.map((w) => (
              <li key={w.code}><Alert tone="warning" title={w.code.replaceAll("_", " ")}>{w.message}</Alert></li>
            ))}
          </ul>
        )}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Document type" hint={doc.doc_type_source === "auto" ? "Suggested automatically" : "Set by a reviewer"}>
            {(p) => <Select {...p} value={docType} onChange={(e) => setDocType(e.target.value)}>
              {DOC_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}
          </Field>
          <Field label="Access level">
            {(p) => <Select {...p} value={access} onChange={(e) => setAccess(e.target.value as typeof access)}>
              {ACCESS_LEVELS.filter(([l]) => l !== "confidential" || can("knowledge.confidential")).map(([l, label]) => <option key={l} value={l}>{label}</option>)}
            </Select>}
          </Field>
          <Field label="Effective date (optional)">
            {(p) => <Input {...p} type="date" value={effective} onChange={(e) => setEffective(e.target.value)} />}
          </Field>
          <Field label="Replaces (optional)" hint="The older document becomes superseded when you approve.">
            {(p) => <Select {...p} value={supersedes} onChange={(e) => setSupersedes(e.target.value)}>
              <option value="">Nothing</option>
              {others?.filter((o) => o.id !== doc.id).map((o) => <option key={o.id} value={o.id}>{o.title}</option>)}
            </Select>}
          </Field>
        </div>
        <Field label="Review note (optional)">
          {(p) => <Textarea {...p} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />}
        </Field>
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => decide("approve")} loading={busy === "approve"} disabled={!!busy}><Check /> Approve and index</Button>
          <Button variant="danger" onClick={() => decide("reject")} loading={busy === "reject"} disabled={!!busy}>Reject</Button>
        </div>
      </div>
    </Card>
  );
}

function Actions({ doc, onChange }: { doc: DocumentDetail; onChange: () => void }) {
  const { can } = useSession();
  const file = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const run = async (path: string) => {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/v1/documents/${doc.id}/${path}`, { method: "POST", org: true });
      onChange();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const newVersion = (f: File) => {
    const form = new FormData();
    form.append("file", f);
    setError(null);
    setProgress(0);
    uploadWithProgress(`/api/v1/documents/${doc.id}/versions`, form, (x) => setProgress(Math.round(x * 100)))
      .promise.then(onChange).catch((err) => setError(errorMessage(err))).finally(() => setProgress(null));
  };
  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => downloadVersion(doc.id).catch((err) => setError(errorMessage(err)))}>
          <Download /> Download
        </Button>
        {doc.status === "failed" && can("knowledge.upload") && <Button variant="secondary" onClick={() => run("retry")} loading={busy}><RefreshCw /> Retry</Button>}
        {["indexed", "awaiting_review"].includes(doc.status) && can("knowledge.review") && (
          <Button variant="secondary" onClick={() => run("reprocess")} loading={busy}><RefreshCw /> Reprocess</Button>)}
        {doc.source_type === "upload" && !isBusy(doc) && doc.status !== "archived" && can("knowledge.upload") && (
          <>
            <Button variant="secondary" onClick={() => file.current?.click()} loading={progress !== null}>
              <Upload /> {progress !== null ? `${progress}%` : "New version"}
            </Button>
            <input ref={file} type="file" className="sr-only" aria-label="Upload a new version"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) newVersion(f); e.target.value = ""; }} />
          </>
        )}
        {can("knowledge.review") && !isBusy(doc) && (doc.status === "archived"
          ? <Button variant="secondary" onClick={() => run("restore")} loading={busy}>Restore</Button>
          : <Button variant="ghost" onClick={() => window.confirm("Archive this document? AI employees will stop using it.") && run("archive")} loading={busy}>Archive</Button>)}
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </div>
  );
}

function downloadVersion(docId: string, versionId?: string) {
  return downloadFile(`/api/v1/documents/${docId}/download${versionId ? `?version_id=${versionId}` : ""}`, "document");
}

function Sections({ doc }: { doc: DocumentDetail }) {
  const { data } = useOrgData<Chunk[]>(doc.chunk_count ? `/api/v1/documents/${doc.id}/chunks` : null);
  const [all, setAll] = useState(false);
  if (!doc.chunk_count) return null;
  const shown = all ? data : data?.slice(0, 6);
  return (
    <Card>
      <CardHeader title={`Extracted sections (${doc.chunk_count})`} description="Exactly what retrieval searches and what answers can cite." />
      <ol className="divide-y divide-border">
        {shown?.map((c) => (
          <li key={c.id} className="px-5 py-3">
            <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="font-medium text-fg">#{c.chunk_index + 1}</span>
              {c.section && <span>{c.section}</span>}
              {c.page_number && <span>Page {c.page_number}</span>}
              {c.kind === "table" && <Badge>Table</Badge>}
              {c.flags.includes("instruction_like_text") && <Badge tone="warning">Instruction-like text removed before AI use</Badge>}
            </div>
            {/* The stored text starts with the heading path (it helps retrieval); it's already shown above. */}
            <p className="line-clamp-4 whitespace-pre-line text-sm text-fg/90">
              {c.section && c.content.startsWith(`${c.section}\n\n`) ? c.content.slice(c.section.length + 2) : c.content}
            </p>
          </li>
        ))}
      </ol>
      {data && data.length > 6 && (
        <div className="border-t border-border px-5 py-3">
          <Button variant="ghost" size="sm" onClick={() => setAll((v) => !v)}>{all ? "Show fewer" : `Show all ${data.length}`}</Button>
        </div>
      )}
    </Card>
  );
}

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const path = `/api/v1/documents/${id}`;
  const { data: doc, error } = useOrgData<DocumentDetail>(path, pollWhile<DocumentDetail>(isBusy));
  const refresh = () => {
    void mutate([path, orgId]);
    void mutate([`${path}/chunks`, orgId]);
  };

  if (error) return <ErrorState error={error} />;
  if (!doc) return <Spinner label="Loading document" />;
  return (
    <>
      <Link href="/app/knowledge" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-fg"><ArrowLeft className="size-4" /> Documents</Link>
      <PageHeader
        eyebrow={DOC_TYPE_LABEL[doc.doc_type] ?? doc.doc_type}
        title={doc.title}
        description={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={doc.status} /><AccessBadge level={doc.access_level} />
          {doc.subject && <span>{doc.subject}</span>}</span>}
        actions={<Actions doc={doc} onChange={refresh} />}
      />
      {doc.status === "failed" && (
        <Alert tone="danger" title="Processing failed" className="mb-6">
          {doc.error_message} {doc.error_code === "no_text_ocr_unavailable" && "Upload a text-based version, or ask your administrator to enable OCR."}
        </Alert>
      )}
      {isBusy(doc) && <Progress doc={doc} />}
      {doc.status === "awaiting_review" && can("knowledge.review") && <ReviewPanel key={doc.updated_at} doc={doc} onDone={refresh} />}
      {doc.status === "awaiting_review" && !can("knowledge.review") && (
        <Alert tone="info" className="mb-6">Waiting for a manager to review it. Until then AI employees and answers don&apos;t use it.</Alert>
      )}
      {doc.superseded_by.length > 0 && (
        <Alert tone="warning" className="mb-6" title="Replaced by a newer document">
          {doc.superseded_by.map((d) => <Link key={d.id} href={`/app/knowledge/${d.id}`} className="mr-3 underline">{d.title}</Link>)}
        </Alert>
      )}
      <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Details" />
            <dl className="px-5 py-3">
              <Meta label="Source">{doc.source_type === "url" ? <span className="ident">{doc.source_url}</span> : doc.original_filename}</Meta>
              <Meta label="Effective date">{doc.effective_date ? formatDate(doc.effective_date) : null}</Meta>
              <Meta label="Added">{formatDateTime(doc.created_at)}</Meta>
              <Meta label="Reviewed">{doc.reviewed_at ? formatDateTime(doc.reviewed_at) : null}</Meta>
              <Meta label="Indexed">{doc.indexed_at ? formatDateTime(doc.indexed_at) : null}</Meta>
              {doc.review_note && <Meta label="Review note">{doc.review_note}</Meta>}
            </dl>
            {doc.status !== "awaiting_review" && doc.summary && (
              <div className="border-t border-border px-5 py-3">
                <p className="text-sm">{doc.summary}</p>
                {doc.summary_label && <p className="mt-1 text-xs text-subtle">{doc.summary_label}</p>}
              </div>
            )}
            {doc.status !== "awaiting_review" && doc.warnings.length > 0 && (
              <ul className="space-y-1 border-t border-border px-5 py-3 text-sm text-warning">
                {doc.warnings.map((w) => <li key={w.code} className="flex gap-2"><AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />{w.message}</li>)}
              </ul>
            )}
          </Card>
          <Card>
            <CardHeader title="Versions" description="Every uploaded file is kept; only the latest is indexed." />
            <Table label="Versions">
              <thead><tr><th className={th}>Version</th><th className={th}>File</th><th className={th}><span className="sr-only">Download</span></th></tr></thead>
              <tbody>
                {doc.versions.map((v) => (
                  <tr key={v.id}>
                    <td className={td}>v{v.version_no}<p className="text-xs text-muted">{formatDateTime(v.created_at)}</p></td>
                    <td className={td}>
                      {v.detected_format.toUpperCase()} · {formatBytes(v.size_bytes)}{v.page_count ? ` · ${v.page_count} pages` : ""}
                      <p className="ident text-xs text-subtle" title="SHA-256">{v.sha256.slice(0, 16)}…</p>
                    </td>
                    <td className={`${td} text-right`}>
                      <Button variant="ghost" size="icon" aria-label={`Download version ${v.version_no}`}
                        onClick={() => downloadVersion(doc.id, v.id).catch(() => window.alert("Download failed"))}><Download /></Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
        <Sections doc={doc} />
      </div>
    </>
  );
}
