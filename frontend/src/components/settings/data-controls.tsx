"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { formatBytes } from "@/components/knowledge/shared";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, ErrorState, Spinner, Table, td, th } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/form";
import { api } from "@/lib/api";
import { downloadFile } from "@/lib/download";
import { pollWhile, useAction, useOrgData } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { DeletionStatus, OrgExport, Retention } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const EXPORT_TONE: Record<OrgExport["status"], "neutral" | "info" | "success" | "danger"> = {
  queued: "info", building: "info", ready: "success", failed: "danger", expired: "neutral",
};

function RetentionForm({ data }: { data: Retention }) {
  const { can, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const [notif, setNotif] = useState(String(data.notifications_days));
  const [ask, setAsk] = useState(String(data.ask_history_days));
  const [reports, setReports] = useState(data.reports_days === null ? "" : String(data.reports_days));
  const a = useAction();
  const editable = can("org.manage");
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        void a.run(async () => {
          await api("/api/v1/org/retention", { method: "PUT", org: true, body: {
            notifications_days: Number(notif), ask_history_days: Number(ask),
            reports_days: reports.trim() ? Number(reports) : null,
          } });
          await mutate(["/api/v1/org/retention", orgId]);
        }, "Retention settings saved.");
      }}
    >
      <h3 className="text-sm font-semibold">Retention</h3>
      <p className="text-sm text-muted">
        Older items are removed automatically once an hour. Minimum 30 days (90 for reports).
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Notifications (days)">
          {(p) => <Input {...p} type="number" min={30} max={3650} required value={notif} disabled={!editable} onChange={(e) => setNotif(e.target.value)} />}
        </Field>
        <Field label="Ask history (days)">
          {(p) => <Input {...p} type="number" min={30} max={3650} required value={ask} disabled={!editable} onChange={(e) => setAsk(e.target.value)} />}
        </Field>
        <Field label="Daily reports (days)" hint="Leave empty to keep them.">
          {(p) => <Input {...p} type="number" min={90} max={3650} value={reports} disabled={!editable} onChange={(e) => setReports(e.target.value)} />}
        </Field>
      </div>
      {editable && <Button type="submit" variant="secondary" loading={a.busy}>Save retention</Button>}
      {a.error && <Alert tone="danger">{a.error}</Alert>}
      {a.done && <Alert tone="success">{a.done}</Alert>}
      <details className="text-sm">
        <summary className="cursor-pointer text-muted">Kept while the workspace exists</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
          {data.kept.map((k) => <li key={k}>{k}</li>)}
        </ul>
      </details>
    </form>
  );
}

function Exports() {
  const { orgId } = useSession();
  const { mutate } = useSWRConfig();
  const { data, error } = useOrgData<OrgExport[]>("/api/v1/org/exports",
    pollWhile((rows: OrgExport[]) => rows.some((x) => x.status === "queued" || x.status === "building")));
  const a = useAction();
  const dl = useAction();
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">Export</h3>
      <p className="text-sm text-muted">
        A zip with every record of this workspace as JSON and the original documents. Downloads expire after a few days.
      </p>
      <Button variant="secondary" loading={a.busy}
        onClick={() => a.run(async () => {
          await api("/api/v1/org/exports", { method: "POST", org: true });
          await mutate(["/api/v1/org/exports", orgId]);
        }, "Export started.")}>
        Export workspace data
      </Button>
      {a.error && <Alert tone="danger">{a.error}</Alert>}
      {a.done && <Alert tone="success">{a.done}</Alert>}
      {error ? <ErrorState error={error} /> : !data ? <Spinner /> : data.length > 0 && (
        <Table label="Workspace exports">
          <thead>
            <tr><th className={th}>Requested</th><th className={th}>Status</th><th className={th}>Size</th><th className={th}>Available until</th><th className={th}><span className="sr-only">Download</span></th></tr>
          </thead>
          <tbody>
            {data.map((x) => (
              <tr key={x.id}>
                <td className={td}>{formatDateTime(x.created_at)}</td>
                <td className={td}><Badge tone={EXPORT_TONE[x.status]}>{x.status}</Badge></td>
                <td className={td}>{x.size_bytes ? formatBytes(x.size_bytes) : "—"}</td>
                <td className={td}>{x.status === "ready" ? formatDateTime(x.expires_at) : "—"}</td>
                <td className={`${td} text-right`}>
                  {x.status === "ready" && (
                    <Button variant="ghost" size="sm" disabled={dl.busy}
                      onClick={() => dl.run(() => downloadFile(`/api/v1/org/exports/${x.id}/download`, "export.zip"))}>
                      <Download /> Download
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {dl.error && <Alert tone="danger">{dl.error}</Alert>}
    </div>
  );
}

function Deletion({ status }: { status: DeletionStatus }) {
  const { membership, can, refresh, orgId } = useSession();
  const { mutate } = useSWRConfig();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const a = useAction();
  const orgName = membership?.organization.name ?? "";
  const reload = async () => {
    await mutate(["/api/v1/org/deletion", orgId]);
    await refresh();
  };
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-danger">Delete workspace</h3>
      {status.scheduled_for ? (
        <>
          <Alert tone="danger">
            This workspace and everything in it — documents, agents, runs, reports and records — will be permanently
            deleted on {formatDateTime(status.scheduled_for)}. Export it first if you need a copy.
          </Alert>
          {can("org.delete") && (
            <Button variant="secondary" loading={a.busy}
              onClick={() => a.run(async () => {
                await api("/api/v1/org/deletion", { method: "DELETE", org: true });
                await reload();
              }, "Deletion cancelled.")}>
              Cancel deletion
            </Button>
          )}
        </>
      ) : !can("org.delete") ? (
        <p className="text-sm text-muted">Only owners can delete a workspace.</p>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            void a.run(async () => {
              await api("/api/v1/org/deletion", { method: "POST", org: true, body: { confirm_name: name, password } });
              setPassword("");
              await reload();
            });
          }}
        >
          <p className="text-sm text-muted">
            Deletion happens {status.grace_hours} hours after you confirm; every owner is emailed and can cancel until
            then. Afterwards nothing can be recovered. Members keep their accounts.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={`Type the workspace name (${orgName})`}>
              {(p) => <Input {...p} autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} />}
            </Field>
            <Field label="Your password">
              {(p) => <Input {...p} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}
            </Field>
          </div>
          <Button type="submit" variant="danger" loading={a.busy} disabled={name !== orgName || !password}>
            Schedule deletion
          </Button>
        </form>
      )}
      {a.error && <Alert tone="danger">{a.error}</Alert>}
      {a.done && <Alert tone="success">{a.done}</Alert>}
    </div>
  );
}

export function DataControlsCard() {
  const { can } = useSession();
  const retention = useOrgData<Retention>("/api/v1/org/retention");
  const deletion = useOrgData<DeletionStatus>("/api/v1/org/deletion");
  return (
    <Card>
      <div id="data" />
      <CardHeader title="Data & privacy" description="How long history is kept, a full export, and deleting the workspace." />
      <div className="space-y-8 px-5 py-4">
        {retention.error ? <ErrorState error={retention.error} /> : !retention.data ? <Spinner /> : (
          <RetentionForm key={JSON.stringify(retention.data)} data={retention.data} />
        )}
        {can("org.export") && <Exports />}
        {deletion.error ? <ErrorState error={deletion.error} /> : !deletion.data ? <Spinner /> : (
          <Deletion status={deletion.data} />
        )}
      </div>
    </Card>
  );
}
