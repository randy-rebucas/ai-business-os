"use client";

import { Bell, CheckCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Checkbox, Field, Input, Select } from "@/components/ui/form";
import { Tabs } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { AppNotification, NotificationDelivery, NotificationPrefs } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const TONE = { info: "info", warning: "warning", critical: "danger" } as const;

function Inbox() {
  const { orgId } = useSession();
  const { mutate } = useSWRConfig();
  const { data, error } = useOrgData<AppNotification[]>("/api/v1/notifications", { refreshInterval: 15000 });
  const refresh = () => Promise.all(["/api/v1/notifications", "/api/v1/notifications/unread-count"].map((p) => mutate([p, orgId])));
  const read = async (path: string) => { await api(path, { method: "POST", org: true }); await refresh(); };
  if (error) return <ErrorState error={error} />;
  if (!data) return <Spinner />;
  if (data.length === 0) return <EmptyState icon={Bell} title="No notifications">Approvals, escalations, failed or unverified runs, budgets and daily reports appear here.</EmptyState>;
  return (
    <div className="space-y-3">
      {data.some((n) => !n.read_at) && <Button variant="secondary" size="sm" onClick={() => read("/api/v1/notifications/read-all")}><CheckCheck /> Mark all as read</Button>}
      <ul className="space-y-2">
        {data.map((n) => (
          <li key={n.id}>
            <Card className={`px-5 py-3 ${n.read_at ? "opacity-80" : "border-accent/40"}`}>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={TONE[n.severity]}>{n.severity}</Badge>
                {!n.read_at && <Badge tone="info">New</Badge>}
                {n.link ? <Link href={n.link} onClick={() => !n.read_at && read(`/api/v1/notifications/${n.id}/read`)} className="font-medium text-accent underline underline-offset-2">{n.title}</Link>
                  : <span className="font-medium">{n.title}</span>}
                <span className="text-xs text-muted">{formatDateTime(n.created_at)}</span>
              </div>
              <p className="mt-1 whitespace-pre-line text-sm text-muted">{n.body}</p>
              {!n.read_at && <button type="button" className="mt-1 text-xs text-accent underline underline-offset-2" onClick={() => read(`/api/v1/notifications/${n.id}/read`)}>Mark as read</button>}
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Preferences({ initial }: { initial: NotificationPrefs }) {
  const { orgId } = useSession();
  const { mutate } = useSWRConfig();
  const [p, setP] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await api("/api/v1/notifications/preferences", { method: "PUT", org: true, body: {
        email_immediate: p.email_immediate, email_digest: p.email_digest, digest_time: p.digest_time,
        sms_critical: p.sms_critical, sms_number: p.sms_number || null } });
      await mutate(["/api/v1/notifications/preferences", orgId]);
      setMsg({ tone: "success", text: "Saved." });
    } catch (err) {
      setMsg({ tone: "danger", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <CardHeader title="How you're notified" description="In-app notifications are always on. Times are in the company's time zone." />
      <form onSubmit={save} className="space-y-4 px-5 py-4">
        <Field label="Email me immediately for">{(f) => (
          <Select {...f} value={p.email_immediate} onChange={(e) => setP({ ...p, email_immediate: e.target.value as NotificationPrefs["email_immediate"] })}>
            <option value="critical">Critical alerts only</option>
            <option value="warning">Critical alerts and items needing action</option>
            <option value="off">Nothing (digest only)</option>
          </Select>)}</Field>
        <Checkbox label="Daily email digest" hint="Everything you haven't had in a digest yet, once a day." checked={p.email_digest} onChange={(e) => setP({ ...p, email_digest: e.target.checked })} />
        <Field label="Digest time" className="w-40">{(f) => <Input {...f} type="time" value={p.digest_time} onChange={(e) => setP({ ...p, digest_time: e.target.value })} />}</Field>
        <Checkbox label="Text me critical alerts" hint={p.sms_provider === "dev" ? "SMS uses the development adapter: messages are stored, not sent." : p.sms_provider === "none" ? "No SMS provider is configured, so texts can't be sent yet." : undefined}
          checked={p.sms_critical} onChange={(e) => setP({ ...p, sms_critical: e.target.checked })} />
        <Field label="Mobile number" hint="International format, e.g. +639171234567" className="w-64">{(f) => <Input {...f} value={p.sms_number ?? ""} onChange={(e) => setP({ ...p, sms_number: e.target.value })} />}</Field>
        {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
        <Button type="submit" loading={busy}>Save preferences</Button>
      </form>
    </Card>
  );
}

function Deliveries() {
  const { data, error } = useOrgData<NotificationDelivery[]>("/api/v1/notifications/deliveries");
  if (error) return <ErrorState error={error} />;
  if (!data) return <Spinner />;
  if (data.length === 0) return <p className="text-sm text-muted">Nothing has been sent to you by email or SMS yet.</p>;
  return (
    <Table label="Deliveries">
      <thead><tr><th className={th}>When</th><th className={th}>Channel</th><th className={th}>Subject</th><th className={th}>Status</th></tr></thead>
      <tbody>
        {data.map((d) => (
          <tr key={d.id}>
            <td className={td}><span className="text-xs">{formatDateTime(d.created_at)}</span></td>
            <td className={td}>{d.channel} · {d.kind}<div className="text-xs text-muted">{d.provider} → {d.to_address}</div></td>
            <td className={td}>{d.subject}</td>
            <td className={td}><Badge tone={d.status === "sent" ? "success" : ["failed", "abandoned"].includes(d.status) ? "danger" : d.status === "suppressed" ? "warning" : "neutral"}>{d.status}</Badge>
              {d.attempts > 1 && <div className="text-xs text-muted">{d.attempts} attempts</div>}
              {d.last_error && <div className="text-xs text-muted">{d.last_error}</div>}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export default function NotificationsPage() {
  const prefs = useOrgData<NotificationPrefs>("/api/v1/notifications/preferences");
  return (
    <>
      <PageHeader title="Notifications"
        description="Alerts about approvals, escalations, failed or unverified work, budgets and daily reports — sent to the people whose permissions let them act." />
      <Tabs label="Notifications" items={[
        { key: "inbox", label: "Inbox", content: <Inbox /> },
        { key: "prefs", label: "Preferences", content: prefs.error ? <ErrorState error={prefs.error} /> : !prefs.data ? <Spinner />
          : <Preferences initial={prefs.data} /> },
        { key: "deliveries", label: "Delivery log", content: <Deliveries /> },
      ]} />
    </>
  );
}
