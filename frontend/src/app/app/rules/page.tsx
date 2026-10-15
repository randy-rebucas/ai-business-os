"use client";

import { Check, Plus, RefreshCw, Scale, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Spinner } from "@/components/ui/display";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { AGENT_SHORT, RULE_KIND, RULE_STATUS } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { BusinessRule, RuleExtraction, RuleStatus } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const PATH = "/api/v1/rules";
const VIEWS: { key: string; label: string; statuses: RuleStatus[] }[] = [
  { key: "review", label: "Needs review", statuses: ["conflicting", "unresolved", "proposed", "fact"] },
  { key: "confirmed", label: "Confirmed", statuses: ["confirmed"] },
  { key: "rejected", label: "Rejected", statuses: ["rejected"] },
];
const SOURCE_LABEL = { document: "Document", interview: "Interview answer", profile: "Company profile", manual: "Added by hand" };

function RuleCard({ rule, all, canReview, onChange }: { rule: BusinessRule; all: BusinessRule[]; canReview: boolean; onChange: () => void }) {
  const [mode, setMode] = useState<"view" | "confirm">("view");
  const [statement, setStatement] = useState(rule.statement);
  const [resolution, setResolution] = useState(rule.resolution ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const st = RULE_STATUS[rule.status];
  const review = async (decision: "confirm" | "reject") => {
    setBusy(true);
    setError(null);
    try {
      await api(`${PATH}/${rule.id}/review`, { method: "POST", org: true, body: {
        decision, resolution: decision === "confirm" ? resolution.trim() || null : null,
        statement: decision === "confirm" && statement.trim() !== rule.statement ? statement.trim() : null,
      } });
      onChange();
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };
  const conflicts = all.filter((r) => rule.conflicts_with.includes(r.id));
  return (
    <Card className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={st.tone}>{st.label}</Badge>
        <Badge>{RULE_KIND[rule.kind] ?? rule.kind}</Badge>
        <span className="text-xs text-muted">{SOURCE_LABEL[rule.source_type]}</span>
        {rule.access_level !== "general" && <Badge tone="warning">{rule.access_level}</Badge>}
        {rule.label && <Badge tone="warning">Development adapter</Badge>}
      </div>
      <h3 className="mt-2 font-medium text-fg">{rule.title}</h3>
      <p className="mt-1 text-sm">{rule.statement}</p>
      {rule.resolution && <p className="mt-1 text-sm"><span className="text-muted">Answer: </span>{rule.resolution}</p>}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {rule.threshold_amount && <span>Threshold: <strong className="text-fg">{Number(rule.threshold_amount).toLocaleString()} {rule.threshold_currency}</strong> (read from the text)</span>}
        <span>Applies to: {rule.applies_to.length ? rule.applies_to.map((a) => AGENT_SHORT[a] ?? a).join(", ") : "all agents"}</span>
        {rule.reviewed_at && <span>Reviewed {formatDateTime(rule.reviewed_at)}</span>}
      </div>
      {rule.stale && <Alert tone="warning" className="mt-3" title="Outdated source">{rule.stale}. Confirmed rules resting on it are no longer applied.</Alert>}
      {rule.citations.map((c) => (
        <figure key={c.chunk_id} className="mt-3 border-l-2 border-border-strong pl-3">
          <blockquote className="text-sm text-fg/85">“{c.quote}”</blockquote>
          <figcaption className="mt-0.5 text-xs text-muted">
            <Link href={`/app/knowledge/${c.document_id}`} className="text-accent underline underline-offset-2">{c.document_title}</Link>
            {c.section && ` · ${c.section}`} · v{c.version_no}
          </figcaption>
        </figure>
      ))}
      {conflicts.length > 0 && (
        <div className="mt-3 text-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-danger">Disagrees with</p>
          <ul className="mt-1 list-disc pl-5">{conflicts.map((c) => <li key={c.id}>{c.statement} <span className="text-xs text-muted">({RULE_STATUS[c.status].label})</span></li>)}</ul>
        </div>
      )}
      {canReview && rule.status !== "confirmed" && rule.status !== "rejected" && (
        mode === "view" ? (
          <div className="mt-4 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setMode("confirm")}><Check /> {rule.status === "unresolved" ? "Answer & confirm" : "Confirm as rule"}</Button>
            <Button size="sm" variant="ghost" onClick={() => review("reject")} disabled={busy}><X /> Reject</Button>
          </div>
        ) : (
          <form className="mt-4 space-y-3" onSubmit={(e) => { e.preventDefault(); void review("confirm"); }}>
            <Field label="Rule as AI employees should follow it">{(p) => <Textarea {...p} rows={2} value={statement} onChange={(e) => setStatement(e.target.value)} />}</Field>
            <Field label={rule.status === "unresolved" ? "Your answer" : "Note (optional)"}>{(p) => <Textarea {...p} rows={2} value={resolution} onChange={(e) => setResolution(e.target.value)} />}</Field>
            <div className="flex gap-2">
              <Button type="submit" size="sm" loading={busy} disabled={rule.status === "unresolved" && !resolution.trim()}>Confirm</Button>
              <Button size="sm" variant="ghost" onClick={() => setMode("view")}>Cancel</Button>
            </div>
          </form>
        )
      )}
      {canReview && rule.status === "confirmed" && (
        <div className="mt-3"><Button size="sm" variant="ghost" onClick={() => review("reject")} disabled={busy}>Withdraw rule</Button></div>
      )}
      {error && <Alert tone="danger" className="mt-3">{error}</Alert>}
    </Card>
  );
}

function AddRule({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [title, setTitle] = useState("");
  const [statement, setStatement] = useState("");
  const [kind, setKind] = useState("policy");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(PATH, { method: "POST", org: true, body: { title, statement, kind } });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="mb-6 w-full">
      <CardHeader title="Add a rule" description="Rules you type in are confirmed immediately." />
      <form className="grid gap-4 px-5 py-4 md:grid-cols-[1fr_12rem]" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <Field label="Title">{(p) => <Input {...p} value={title} onChange={(e) => setTitle(e.target.value)} />}</Field>
        <Field label="Kind">{(p) => <Select {...p} value={kind} onChange={(e) => setKind(e.target.value)}>
          {Object.entries(RULE_KIND).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>}</Field>
        <Field label="Rule" className="md:col-span-2">{(p) => <Textarea {...p} rows={2} value={statement} onChange={(e) => setStatement(e.target.value)} />}</Field>
        {error && <Alert tone="danger" className="md:col-span-2">{error}</Alert>}
        <div className="flex gap-2 md:col-span-2">
          <Button type="submit" loading={busy} disabled={title.trim().length < 3 || statement.trim().length < 3}>Add rule</Button>
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        </div>
      </form>
    </Card>
  );
}

export default function RulesPage() {
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const { data, error } = useOrgData<BusinessRule[]>(PATH);
  const [view, setView] = useState("review");
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<RuleExtraction | null>(null);
  const [extractError, setExtractError] = useState<string | null>(null);
  const canReview = can("rule.review");
  const refresh = () => mutate([PATH, orgId]);
  const extract = async () => {
    setBusy(true);
    setExtractError(null);
    try {
      setReport(await api<RuleExtraction>(`${PATH}/extract`, { method: "POST", org: true }));
      await refresh();
    } catch (err) {
      setExtractError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const current = VIEWS.find((v) => v.key === view)!;
  const shown = (data ?? []).filter((r) => current.statuses.includes(r.status))
    .sort((a, b) => current.statuses.indexOf(a.status) - current.statuses.indexOf(b.status));
  return (
    <>
      <PageHeader title="Business rules"
        description="Rules found in your approved documents, interview answers and profile. Nothing is enforced until you confirm it — facts, proposals, open questions and conflicts are kept apart."
        actions={canReview && <>
          <Button variant="secondary" onClick={() => setAdding(true)} disabled={adding}><Plus /> Add a rule</Button>
          <Button onClick={extract} loading={busy}><RefreshCw /> Extract from knowledge</Button>
        </>} />
      {adding && <AddRule onCancel={() => setAdding(false)} onDone={() => { setAdding(false); setView("confirmed"); void refresh(); }} />}
      {report && (
        <Alert tone={report.label ? "warning" : "info"} className="mb-4" title={`${report.created} new item${report.created === 1 ? "" : "s"} from ${report.sources_considered} document passage${report.sources_considered === 1 ? "" : "s"}`}>
          {report.conflicts > 0 && <p>{report.conflicts} conflict flag(s) raised.</p>}
          {report.dropped.length > 0 && <p>{report.dropped.length} item(s) dropped because they didn&apos;t match their source.</p>}
          {report.label && <p>{report.label}. Real interpretation needs a connected AI model; this lists rule-like sentences verbatim.</p>}
        </Alert>
      )}
      {extractError && <Alert tone="danger" className="mb-4">{extractError}</Alert>}
      <div role="group" aria-label="Filter rules" className="mb-5 flex flex-wrap gap-2">
        {VIEWS.map((v) => {
          const count = (data ?? []).filter((r) => v.statuses.includes(r.status)).length;
          return <Button key={v.key} size="sm" variant={view === v.key ? "primary" : "secondary"} aria-pressed={view === v.key} onClick={() => setView(v.key)}>{v.label} ({count})</Button>;
        })}
      </div>
      {error ? <ErrorState error={error} /> : !data ? <Spinner /> : shown.length === 0 ? (
        <EmptyState icon={Scale} title={view === "review" ? "Nothing waiting for review" : `No ${current.label.toLowerCase()} rules`}
          action={canReview && view === "review" && <Button onClick={extract} loading={busy}>Extract from knowledge</Button>}>
          {view === "review" ? <>Approve documents in the <Link href="/app/knowledge" className="underline">knowledge base</Link> and answer the <Link href="/app/interview" className="underline">business interview</Link>, then extract.</> : null}
        </EmptyState>
      ) : (
        <div className="space-y-3">{shown.map((r) => <RuleCard key={`${r.id}-${r.status}-${r.reviewed_at}`} rule={r} all={data} canReview={canReview} onChange={refresh} />)}</div>
      )}
    </>
  );
}
