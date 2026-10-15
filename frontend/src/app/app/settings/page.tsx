"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Field, Input, Select } from "@/components/ui/form";
import { DataControlsCard } from "@/components/settings/data-controls";
import { api } from "@/lib/api";
import { useAction, useGlobalData, useOrgData } from "@/lib/hooks";
import { ROLE_HELP, ROLE_LABEL } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { Member, OrgRole, SessionInfo } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const ROLES: OrgRole[] = ["owner", "admin", "manager", "member", "viewer"];

function WorkspaceCard() {
  const { membership, can, refresh } = useSession();
  const [name, setName] = useState(membership?.organization.name ?? "");
  const a = useAction();
  return (
    <Card>
      <CardHeader title="Workspace" description={`Slug: ${membership?.organization.slug}`} />
      <form
        className="flex flex-wrap items-end gap-3 px-5 py-4"
        onSubmit={(e) => {
          e.preventDefault();
          void a.run(async () => {
            await api("/api/v1/org", { method: "PATCH", org: true, body: { name } });
            await refresh();
          }, "Workspace renamed.");
        }}
      >
        <Field label="Workspace name" className="min-w-64 flex-1">
          {(p) => <Input {...p} value={name} disabled={!can("org.manage")} onChange={(e) => setName(e.target.value)} />}
        </Field>
        {can("org.manage") && <Button type="submit" loading={a.busy}>Save</Button>}
      </form>
      <div className="px-5 pb-4">
        {a.error && <Alert tone="danger">{a.error}</Alert>}
        {a.done && <Alert tone="success">{a.done}</Alert>}
      </div>
    </Card>
  );
}

function MemberRow({ m, canManage, canOwners, onChange }: { m: Member; canManage: boolean; canOwners: boolean; onChange: () => void }) {
  const { me } = useSession();
  const [title, setTitle] = useState(m.job_title ?? "");
  const a = useAction();
  const editable = canManage && (canOwners || m.role !== "owner");
  const patch = (body: Record<string, unknown>) =>
    a.run(async () => {
      await api(`/api/v1/org/members/${m.user_id}`, { method: "PATCH", org: true, body });
      onChange();
    });
  return (
    <tr>
      <td className={td}>
        <p className="font-medium">{m.full_name}{m.user_id === me.user.id && <span className="text-muted"> (you)</span>}</p>
        <p className="text-xs text-muted">{m.email}</p>
        {a.error && <p className="mt-1 text-xs text-danger">{a.error}</p>}
      </td>
      <td className={td}>
        {editable ? (
          <Input aria-label={`Job title for ${m.full_name}`} className="h-8 max-w-48" value={title} placeholder="—"
            onChange={(e) => setTitle(e.target.value)}
            onBlur={() => title.trim() !== (m.job_title ?? "") &&
              void patch(title.trim() ? { job_title: title.trim() } : { clear_job_title: true })} />
        ) : (
          m.job_title ?? <span className="text-subtle">—</span>
        )}
      </td>
      <td className={td}>
        {editable ? (
          <Select aria-label={`Role for ${m.full_name}`} className="h-8 w-32" value={m.role} disabled={a.busy}
            onChange={(e) => void patch({ role: e.target.value })}>
            {ROLES.filter((r) => canOwners || r !== "owner").map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </Select>
        ) : (
          <Badge tone={m.role === "owner" ? "info" : "neutral"}>{ROLE_LABEL[m.role]}</Badge>
        )}
      </td>
      <td className={`${td} text-right`}>
        {editable && m.user_id !== me.user.id && (
          <Button variant="ghost" size="icon" aria-label={`Remove ${m.full_name}`} disabled={a.busy}
            onClick={() => window.confirm(`Remove ${m.full_name} from this workspace?`) &&
              void a.run(async () => {
                await api(`/api/v1/org/members/${m.user_id}`, { method: "DELETE", org: true });
                onChange();
              })}>
            <Trash2 />
          </Button>
        )}
      </td>
    </tr>
  );
}

function MembersCard() {
  const { can, orgId, refresh } = useSession();
  const { mutate } = useSWRConfig();
  const { data, error } = useOrgData<Member[]>("/api/v1/org/members");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrgRole>("member");
  const [title, setTitle] = useState("");
  const a = useAction();
  const reload = () => {
    void mutate(["/api/v1/org/members", orgId]);
    void refresh();
  };
  const canManage = can("org.members.manage");
  const canOwners = can("org.members.manage_owners");

  return (
    <Card>
      <CardHeader title="Members" description="Roles control what people can do in this workspace. Job titles are labels only." />
      <div className="space-y-4 px-5 py-4">
        {error ? <ErrorState error={error} /> : !data ? <Spinner /> : (
          <Table label="Workspace members">
            <thead>
              <tr><th className={th}>Person</th><th className={th}>Title</th><th className={th}>Role</th><th className={th}><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {data.map((m) => (
                <MemberRow key={`${m.user_id}-${m.role}-${m.job_title}`} m={m} canManage={canManage} canOwners={canOwners} onChange={reload} />
              ))}
            </tbody>
          </Table>
        )}
        {canManage && (
          <form
            className="grid gap-3 rounded-md border border-border bg-surface/60 p-4 sm:grid-cols-[1fr_9rem_10rem_auto] sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              void a.run(async () => {
                await api("/api/v1/org/members", { method: "POST", org: true, body: { email, role, job_title: title.trim() || null } });
                setEmail("");
                setTitle("");
                reload();
              }, "Member added.");
            }}
          >
            <Field label="Add by email" hint="They need an account first.">
              {(p) => <Input {...p} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />}
            </Field>
            <Field label="Role">
              {(p) => (
                <Select {...p} value={role} onChange={(e) => setRole(e.target.value as OrgRole)}>
                  {ROLES.filter((r) => canOwners || r !== "owner").map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Title (optional)">
              {(p) => <Input {...p} value={title} onChange={(e) => setTitle(e.target.value)} />}
            </Field>
            <Button type="submit" loading={a.busy}>Add</Button>
          </form>
        )}
        {a.error && <Alert tone="danger">{a.error}</Alert>}
        {a.done && <Alert tone="success">{a.done}</Alert>}
        <details className="text-sm">
          <summary className="cursor-pointer text-muted">What each role can do</summary>
          <dl className="mt-2 space-y-1">
            {ROLES.map((r) => (
              <div key={r} className="flex gap-2"><dt className="w-20 shrink-0 font-medium">{ROLE_LABEL[r]}</dt><dd className="text-muted">{ROLE_HELP[r]}</dd></div>
            ))}
          </dl>
        </details>
      </div>
    </Card>
  );
}

function AccountCard() {
  const { me } = useSession();
  const { mutate } = useSWRConfig();
  const { data: sessions } = useGlobalData<SessionInfo[]>("/api/v1/auth/sessions");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const pw = useAction();
  const verify = useAction();
  const sess = useAction();

  return (
    <Card>
      <div id="account" />
      <CardHeader title="Your account" description={me.user.email} />
      <div className="space-y-6 px-5 py-4">
        {!me.user.email_verified_at && (
          <div className="space-y-2">
            <Alert tone="warning">Your email address is not verified.</Alert>
            <Button variant="secondary" size="sm" loading={verify.busy}
              onClick={() => verify.run(() => api("/api/v1/auth/verify-email/resend", { method: "POST" }), "Verification email sent.")}>
              Resend verification email
            </Button>
            {verify.error && <Alert tone="danger">{verify.error}</Alert>}
            {verify.done && <Alert tone="success">{verify.done}</Alert>}
          </div>
        )}
        <form
          className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            void pw.run(async () => {
              await api("/api/v1/auth/password", { method: "POST", body: { current_password: current, new_password: next } });
              setCurrent("");
              setNext("");
              await mutate(["/api/v1/auth/sessions", null]);
            }, "Password changed. Other sessions were signed out.");
          }}
        >
          <Field label="Current password">
            {(p) => <Input {...p} type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />}
          </Field>
          <Field label="New password" hint="At least 10 characters.">
            {(p) => <Input {...p} type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />}
          </Field>
          <Button type="submit" variant="secondary" loading={pw.busy}>Change password</Button>
        </form>
        {pw.error && <Alert tone="danger">{pw.error}</Alert>}
        {pw.done && <Alert tone="success">{pw.done}</Alert>}

        <div>
          <h3 className="mb-2 text-sm font-semibold">Signed-in sessions</h3>
          <ul className="divide-y divide-border rounded-md border border-border">
            {(sessions ?? []).map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <div className="min-w-0">
                  <p className="truncate">{s.user_agent ?? "Unknown device"}{s.current && <Badge tone="success" className="ml-2">This device</Badge>}</p>
                  <p className="text-xs text-muted">Last active {formatDateTime(s.last_seen_at)}{s.ip && ` · ${s.ip}`}</p>
                </div>
                {!s.current && (
                  <Button variant="ghost" size="sm" disabled={sess.busy}
                    onClick={() => sess.run(async () => {
                      await api(`/api/v1/auth/sessions/${s.id}`, { method: "DELETE" });
                      await mutate(["/api/v1/auth/sessions", null]);
                    })}>
                    Sign out
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {sess.error && <Alert tone="danger" className="mt-2">{sess.error}</Alert>}
        </div>
      </div>
    </Card>
  );
}

function NewWorkspaceCard() {
  const { refresh, switchOrg } = useSession();
  const [name, setName] = useState("");
  const a = useAction();
  return (
    <Card>
      <CardHeader title="Create another workspace" description="For a separate company. You'll be its owner; data is never shared between workspaces." />
      <form
        className="flex flex-wrap items-end gap-3 px-5 py-4"
        onSubmit={(e) => {
          e.preventDefault();
          void a.run(async () => {
            const org = await api<{ id: string }>("/api/v1/orgs", { method: "POST", body: { name } });
            await refresh();
            switchOrg(org.id);
          });
        }}
      >
        <Field label="Company name" className="min-w-64 flex-1">
          {(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Button type="submit" variant="secondary" loading={a.busy} disabled={!name.trim()}>Create workspace</Button>
      </form>
      {a.error && <div className="px-5 pb-4"><Alert tone="danger">{a.error}</Alert></div>}
    </Card>
  );
}

export default function SettingsPage() {
  const { membership } = useSession();
  return (
    <>
      <PageHeader title="Settings" description="Workspace, people, data controls and your own account." />
      <div className="space-y-6">
        {membership && <WorkspaceCard key={membership.organization.id} />}
        {membership && <MembersCard />}
        {membership && <DataControlsCard key={membership.organization.id} />}
        <AccountCard />
        <NewWorkspaceCard />
      </div>
    </>
  );
}
