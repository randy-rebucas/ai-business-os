"use client";

import { Bot, Sparkles, Store } from "lucide-react";
import Link from "next/link";

import { LifecycleBadge, ConfigBadge } from "@/components/agents/shared";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState, ErrorState, PageHeader, Spinner, Table, td, th } from "@/components/ui/display";
import { useOrgData } from "@/lib/hooks";
import { money } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { AgentListItem } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export default function AgentDirectoryPage() {
  const { can } = useSession();
  const { data, error } = useOrgData<AgentListItem[]>("/api/v1/agents");
  const actions = (
    <>
      <ButtonLink href="/app/agents/catalog" variant="secondary"><Store /> Agent catalog</ButtonLink>
      {can("agent.hire") && <ButtonLink href="/app/agents/team"><Sparkles /> Build your team</ButtonLink>}
    </>
  );
  return (
    <>
      <PageHeader eyebrow="AI workforce" title="Agent directory" actions={actions}
        description="Every AI employee hired into this workspace, where it is in its lifecycle, and its current configuration." />
      {error ? <ErrorState error={error} /> : !data ? <Spinner /> : data.length === 0 ? (
        <EmptyState icon={Bot} title="No AI employees yet"
          action={can("agent.hire") && <ButtonLink href="/app/agents/team">See the recommended team</ButtonLink>}>
          Start with a recommended team based on your company profile, or pick agents from the catalog.
        </EmptyState>
      ) : (
        <Table label="AI employees">
          <thead>
            <tr>
              <th className={th}>Agent</th><th className={th}>Status</th><th className={th}>Configuration</th>
              <th className={th}>Tasks</th><th className={th}>Budget / month</th><th className={th}>Since</th>
            </tr>
          </thead>
          <tbody>
            {data.map((a) => (
              <tr key={a.id}>
                <td className={td}>
                  <Link href={`/app/agents/${a.id}`} className="font-medium text-accent underline-offset-2 hover:underline">{a.name}</Link>
                  <div className="text-xs text-muted">{a.department}</div>
                </td>
                <td className={td}><LifecycleBadge status={a.status} /></td>
                <td className={td}>
                  {a.current_version ? <span className="flex flex-wrap items-center gap-2">v{a.current_version} {a.current_config_status && <ConfigBadge status={a.current_config_status} />}</span>
                    : <span className="text-subtle">Not generated</span>}
                </td>
                <td className={td}>{a.task_count || "—"}</td>
                <td className={td}>{a.monthly_budget_usd ? money(a.monthly_budget_usd) : "—"}</td>
                <td className={td}><span className="text-xs text-muted">{formatDateTime(a.status_changed_at)}</span></td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}
