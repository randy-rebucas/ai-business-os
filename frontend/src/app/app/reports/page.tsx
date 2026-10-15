"use client";

import { FileBarChart } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, EmptyState, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { Field, Select } from "@/components/ui/form";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { AgentListItem, DailyReport } from "@/lib/types";
import { formatDate, formatDateTime } from "@/lib/utils";

export default function ReportsPage() {
  const router = useRouter();
  const { can } = useSession();
  const [agentId, setAgentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reports = useOrgData<DailyReport[]>(`/api/v1/reports${agentId ? `?agent_id=${agentId}` : ""}`);
  const agents = useOrgData<AgentListItem[]>("/api/v1/agents");
  const activated = (agents.data ?? []).filter((a) => a.deployment_stage);
  const generate = async () => {
    const target = agentId || activated[0]?.id;
    if (!target) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ id: string }>("/api/v1/reports/generate", { method: "POST", org: true, body: { agent_id: target } });
      router.push(`/app/reports/${r.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };
  return (
    <>
      <PageHeader title="Daily reports"
        description="One report per agent per day, built only from its task runs and recorded tool executions. Each day's report is finalised after midnight in the company's time zone." />
      {error && <Alert tone="danger" className="mb-6">{error}</Alert>}
      <Card className="mb-6">
        <CardHeader title="Filter and build" description="“Build today's report” shows today so far; it is replaced by the final version after midnight." />
        <div className="flex flex-wrap items-end gap-3 px-5 py-4">
          <Field label="Agent" className="w-64">{(p) => (
            <Select {...p} value={agentId} onChange={(e) => setAgentId(e.target.value)}>
              <option value="">All agents</option>
              {(agents.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
          )}</Field>
          {can("task.manage") && activated.length > 0 && (
            <Button variant="secondary" onClick={generate} loading={busy}>
              <FileBarChart /> Build today&apos;s report{agentId ? "" : ` (${activated[0].name})`}
            </Button>
          )}
        </div>
      </Card>
      {reports.error ? <ErrorState error={reports.error} /> : !reports.data ? <Spinner /> : reports.data.length === 0 ? (
        <EmptyState icon={FileBarChart} title="No reports yet">Reports start the day after an agent is activated, or build today&apos;s so far.</EmptyState>
      ) : (
        <Table label="Daily reports">
          <thead><tr><th className={th}>Day</th><th className={th}>Agent</th><th className={th}>Summary</th><th className={th}>Status</th></tr></thead>
          <tbody>
            {reports.data.map((r) => (
              <tr key={r.id}>
                <td className={td}>{can("records.read") ? <Link href={`/app/reports/${r.id}`} className="text-accent underline underline-offset-2">{formatDate(r.report_date)}</Link> : formatDate(r.report_date)}</td>
                <td className={td}>{r.agent_name}</td>
                <td className={td}><span className="text-sm">{r.summary}</span></td>
                <td className={td}>{r.final ? <Badge tone="success">Final</Badge> : <Badge tone="info">So far</Badge>}
                  <div className="text-xs text-muted">v{r.version} · {formatDateTime(r.generated_at)}</div></td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}
