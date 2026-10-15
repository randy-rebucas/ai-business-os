"use client";

import { FileText, Globe, Upload, X } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { useSWRConfig } from "swr";

import { AccessBadge, formatBytes, isBusy, StatusBadge } from "@/components/knowledge/shared";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardHeader, EmptyState, ErrorState, PageHeader, ProgressBar, Spinner, Table, td, th } from "@/components/ui/display";
import { Field, Input, Select } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { pollWhile, useOrgData } from "@/lib/hooks";
import { ACCESS_LEVELS, DOC_STATUS, DOC_TYPE_LABEL, DOC_TYPES } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { AccessLevel, DocumentRow } from "@/lib/types";
import { uploadWithProgress } from "@/lib/upload";
import { cn, formatDateTime } from "@/lib/utils";

const ACCEPT = ".pdf,.docx,.xlsx,.csv,.txt,.md,.markdown";

type Item = { id: number; name: string; size: number; progress: number; state: "uploading" | "done" | "error"; error?: string; docId?: string };

function AccessSelect({ value, onChange }: { value: AccessLevel; onChange: (v: AccessLevel) => void }) {
  const { can } = useSession();
  const allowed: AccessLevel[] = ["general", ...(can("knowledge.review") ? ["restricted" as const] : []),
    ...(can("knowledge.confidential") ? ["confidential" as const] : [])];
  return (
    <Field label="Who may use these documents" hint={ACCESS_LEVELS.find(([l]) => l === value)?.[2]}>
      {(p) => (
        <Select {...p} value={value} onChange={(e) => onChange(e.target.value as AccessLevel)}>
          {ACCESS_LEVELS.filter(([l]) => allowed.includes(l)).map(([l, label]) => <option key={l} value={l}>{label}</option>)}
        </Select>
      )}
    </Field>
  );
}

function UploadPanel({ onUploaded }: { onUploaded: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const seq = useRef(0);
  const [items, setItems] = useState<Item[]>([]);
  const [access, setAccess] = useState<AccessLevel>("general");
  const [effective, setEffective] = useState("");
  const [dragging, setDragging] = useState(false);

  const patch = (id: number, p: Partial<Item>) => setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...p } : x)));

  const start = (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      const id = ++seq.current;
      setItems((xs) => [...xs, { id, name: file.name, size: file.size, progress: 0, state: "uploading" }]);
      const form = new FormData();
      form.append("file", file);
      form.append("access_level", access);
      if (effective) form.append("effective_date", effective);
      uploadWithProgress<DocumentRow>("/api/v1/documents", form, (f) => patch(id, { progress: Math.round(f * 100) }))
        .promise.then((doc) => {
          patch(id, { state: "done", progress: 100, docId: doc.id });
          onUploaded();
        })
        .catch((err) => patch(id, { state: "error", error: errorMessage(err) }));
    }
  };

  return (
    <Card>
      <CardHeader title="Upload documents" description="PDF, DOCX, XLSX, CSV, TXT or Markdown, up to 20 MB each. Nothing is used by AI employees until you review it." />
      <div className="space-y-4 px-5 py-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <AccessSelect value={access} onChange={setAccess} />
          <Field label="Effective date (optional)" hint="When the policy took effect. Helps resolve outdated versions.">
            {(p) => <Input {...p} type="date" value={effective} onChange={(e) => setEffective(e.target.value)} />}
          </Field>
        </div>
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); start(e.dataTransfer.files); }}
          className={cn("flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
            dragging ? "border-accent bg-accent-soft" : "border-border-strong")}
        >
          <Upload className="size-6 text-subtle" aria-hidden />
          <p className="text-sm text-muted">Drag files here, or</p>
          <Button variant="secondary" size="sm" onClick={() => input.current?.click()}>Choose files</Button>
          <input ref={input} type="file" multiple accept={ACCEPT} className="sr-only" aria-label="Choose files to upload"
            onChange={(e) => { if (e.target.files) start(e.target.files); e.target.value = ""; }} />
        </div>
        {items.length > 0 && (
          <ul className="space-y-2" aria-live="polite">
            {items.map((it) => (
              <li key={it.id} className="rounded-md border border-border px-3 py-2 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate font-medium">{it.name}</span>
                  <span className="shrink-0 text-xs text-muted">
                    {formatBytes(it.size)} · {it.state === "uploading" ? `${it.progress}%` : it.state === "done" ? "Uploaded — processing" : "Failed"}
                  </span>
                  {it.state !== "uploading" && (
                    <button type="button" aria-label={`Dismiss ${it.name}`} className="text-subtle hover:text-fg"
                      onClick={() => setItems((xs) => xs.filter((x) => x.id !== it.id))}><X className="size-4" /></button>
                  )}
                </div>
                {it.state === "uploading" && <div className="mt-2"><ProgressBar value={it.progress} label={`Uploading ${it.name}`} /></div>}
                {it.error && <p className="mt-1 text-xs text-danger">{it.error}</p>}
                {it.docId && <Link href={`/app/knowledge/${it.docId}`} className="mt-1 inline-block text-xs text-accent underline-offset-2 hover:underline">Open document</Link>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function UrlPanel({ onAdded }: { onAdded: () => void }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Card>
      <CardHeader title="Import a web page" description="A public page such as your FAQ or terms. It is fetched once; re-import to refresh." />
      <form
        className="space-y-3 px-5 py-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await api("/api/v1/documents/url", { method: "POST", org: true, body: { url } });
            setUrl("");
            onAdded();
          } catch (err) {
            setError(errorMessage(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Page address">
          {(p) => <Input {...p} type="url" placeholder="https://www.example.com/faq" value={url} onChange={(e) => setUrl(e.target.value)} />}
        </Field>
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" variant="secondary" loading={busy} disabled={!url.trim()}><Globe /> Import page</Button>
      </form>
    </Card>
  );
}

export default function DocumentsPage() {
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const params = new URLSearchParams(Object.entries({ status, doc_type: type, q }).filter(([, v]) => v));
  const path = `/api/v1/documents${params.size ? `?${params}` : ""}`;
  const { data, error } = useOrgData<DocumentRow[]>(path, pollWhile<DocumentRow[]>(isBusy));
  const refresh = () => mutate([path, orgId]);
  const awaiting = data?.filter((d) => d.status === "awaiting_review").length ?? 0;

  return (
    <>
      <PageHeader
        eyebrow="Knowledge"
        title="Documents"
        description="Company documents your AI employees can learn from. Each one is read, split into sections and indexed, then waits for your review before anything can use it."
      />
      {can("knowledge.upload") && (
        <div className="mb-6 grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <UploadPanel onUploaded={refresh} />
          <UrlPanel onAdded={refresh} />
        </div>
      )}
      {awaiting > 0 && can("knowledge.review") && (
        <Alert tone="warning" className="mb-4">
          {awaiting} document{awaiting > 1 ? "s are" : " is"} waiting for your review. Open {awaiting > 1 ? "each" : "it"} to confirm the extracted content represents your business.
        </Alert>
      )}
      <div className="mb-3 flex flex-wrap gap-3">
        <Input aria-label="Search titles" placeholder="Search titles" className="w-56" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select aria-label="Filter by status" className="w-48" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {Object.entries(DOC_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </Select>
        <Select aria-label="Filter by type" className="w-48" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">All types</option>
          {DOC_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </Select>
      </div>
      {error ? <ErrorState error={error} /> : !data ? <Spinner /> : data.length === 0 ? (
        <EmptyState icon={FileText} title={params.size ? "No matching documents" : "No documents yet"}>
          {params.size ? "Try other filters." : "Start with the policies and SOPs your team relies on every day."}
        </EmptyState>
      ) : (
        <Table label="Documents">
          <thead>
            <tr><th className={th}>Document</th><th className={th}>Type</th><th className={th}>Status</th><th className={th}>Sections</th><th className={th}>Added</th></tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.id} className="hover:bg-surface/60">
                <td className={td}>
                  <Link href={`/app/knowledge/${d.id}`} className="font-medium text-fg underline-offset-2 hover:underline">{d.title}</Link>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                    <span className="ident">{d.source_type === "url" ? d.source_url : d.original_filename}</span>
                    <AccessBadge level={d.access_level} />
                    {d.warnings.length > 0 && <span className="text-warning">{d.warnings.length} warning{d.warnings.length > 1 && "s"}</span>}
                  </div>
                  {d.status === "failed" && d.error_message && <p className="mt-1 text-xs text-danger">{d.error_message}</p>}
                </td>
                <td className={td}>{DOC_TYPE_LABEL[d.doc_type] ?? d.doc_type}</td>
                <td className={td}><StatusBadge status={d.status} /></td>
                <td className={`${td} tabular-nums`}>{d.chunk_count || "—"}</td>
                <td className={`${td} whitespace-nowrap text-muted`}>{formatDateTime(d.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}
