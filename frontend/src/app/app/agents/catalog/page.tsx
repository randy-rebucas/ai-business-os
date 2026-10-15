"use client";

import { ArrowRight, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Bullets, LifecycleBadge } from "@/components/agents/shared";
import { Button, ButtonLink } from "@/components/ui/button";
import { Alert, Badge, Card, ErrorState, Meta, PageHeader, Spinner } from "@/components/ui/display";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { money } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { AgentDefinition, AgentInstance } from "@/lib/types";

function AgentCard({ d }: { d: AgentDefinition }) {
  const { can } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hire = async () => {
    setBusy(true);
    setError(null);
    try {
      const [inst] = await api<AgentInstance[]>("/api/v1/agents", { method: "POST", org: true, body: { definition_keys: [d.key], source: "custom" } });
      router.push(`/app/agents/${inst.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };
  const hired = d.status !== "available";
  return (
    <Card className="flex flex-col">
      <div className="flex items-start gap-3 border-b border-border px-5 py-4">
        <div aria-hidden className="grid size-10 shrink-0 place-items-center rounded-md bg-accent/10 font-semibold text-accent">{d.letter}</div>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-fg">{d.name}</h2>
          <p className="text-xs text-muted">{d.title} · {d.department}</p>
        </div>
        <LifecycleBadge status={d.status} />
      </div>
      <div className="flex-1 space-y-3 px-5 py-4">
        <p className="text-sm">{d.role_description}</p>
        <ul aria-label="Expertise" className="flex flex-wrap gap-1.5">
          {d.expertise.map((e) => <li key={e}><Badge>{e}</Badge></li>)}
        </ul>
        <details className="group text-sm">
          <summary className="cursor-pointer text-accent underline-offset-2 hover:underline">Full profile</summary>
          <div className="mt-3 space-y-3">
            <div><p className="mb-1 text-xs font-medium uppercase tracking-wide text-subtle">Responsibilities</p><Bullets items={d.responsibilities} /></div>
            <div><p className="mb-1 text-xs font-medium uppercase tracking-wide text-subtle">Never does</p><Bullets items={d.prohibited} /></div>
            <div><p className="mb-1 text-xs font-medium uppercase tracking-wide text-subtle">Escalates when</p><Bullets items={d.escalation_conditions} /></div>
            <div><p className="mb-1 text-xs font-medium uppercase tracking-wide text-subtle">Tools</p><Bullets items={d.tools.map((t) => t.label)} /></div>
            <dl>
              <Meta label="KPIs">{d.kpis.map((k) => `${k.name} (${k.target})`).join("; ")}</Meta>
              <Meta label="Reports">{d.reporting_frequency}</Meta>
              <Meta label="Default mode">{d.default_operating_mode.replaceAll("_", " ")}</Meta>
              <Meta label="Catalog version">v{d.version}</Meta>
            </dl>
          </div>
        </details>
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-border px-5 py-3">
        <span className="text-xs text-muted">Est. {money(d.default_monthly_budget_usd)} / month</span>
        {hired && d.instance_id ? (
          <ButtonLink href={`/app/agents/${d.instance_id}`} size="sm" variant="secondary">Open <ArrowRight /></ButtonLink>
        ) : can("agent.hire") ? (
          <Button size="sm" onClick={hire} loading={busy}><UserPlus /> Hire</Button>
        ) : null}
      </div>
      {error && <Alert tone="danger" className="mx-5 mb-4">{error}</Alert>}
    </Card>
  );
}

export default function CatalogPage() {
  const { data, error } = useOrgData<AgentDefinition[]>("/api/v1/agents/catalog");
  return (
    <>
      <PageHeader title="Agent catalog"
        description={<>Specialised AI employees you can hire. Not sure which ones you need? <Link href="/app/agents/team" className="text-accent underline underline-offset-2">See the recommended team</Link>.</>} />
      {error ? <ErrorState error={error} /> : !data ? <Spinner /> : (
        <div className="grid gap-5 md:grid-cols-2">{data.map((d) => <AgentCard key={d.key} d={d} />)}</div>
      )}
    </>
  );
}
