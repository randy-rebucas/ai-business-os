"use client";

import { Sparkles, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, ErrorState, PageHeader, Spinner } from "@/components/ui/display";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { money } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { Recommendation } from "@/lib/types";
import { cn } from "@/lib/utils";

function TeamBuilder({ rec }: { rec: Recommendation }) {
  const { can } = useSession();
  const router = useRouter();
  const recommended = rec.items.filter((i) => i.recommended && !i.hired).map((i) => i.key);
  const [selected, setSelected] = useState<string[]>(recommended);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toggle = (key: string) => setSelected((s) => (s.includes(key) ? s.filter((k) => k !== key) : [...s, key]));
  const total = rec.items.filter((i) => selected.includes(i.key)).reduce((sum, i) => sum + Number(i.estimated_monthly_usd), 0);
  const isRecommended = selected.length === recommended.length && selected.every((k) => recommended.includes(k));
  const budget = rec.budget;
  const over = budget.status !== "not_comparable" && budget.amount != null && budget.currency === "USD" && total > Number(budget.amount);

  const hire = async () => {
    setBusy(true);
    setError(null);
    try {
      await api("/api/v1/agents", { method: "POST", org: true, body: { definition_keys: selected, source: isRecommended ? "recommended" : "custom" } });
      router.push("/app/agents");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <div className="space-y-4">
        {rec.profile_gaps.length > 0 && (
          <Alert tone="info" title="Better recommendations need more context">
            Add {rec.profile_gaps.join(", ")} in <Link href="/app/onboarding" className="underline underline-offset-2">company setup</Link>.
          </Alert>
        )}
        <fieldset className="space-y-3">
          <legend className="sr-only">Choose agents to hire</legend>
          {rec.items.map((i) => {
            const checked = selected.includes(i.key);
            return (
              <label key={i.key} className={cn("block cursor-pointer rounded-lg border bg-bg-2 px-5 py-4 shadow-sm transition-colors",
                checked ? "border-accent" : "border-border", i.hired && "cursor-default opacity-70")}>
                <div className="flex items-start gap-3">
                  <input type="checkbox" className="mt-1 size-4 accent-accent" checked={checked || i.hired} disabled={i.hired || !can("agent.hire")}
                    onChange={() => toggle(i.key)} aria-describedby={`why-${i.key}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-fg">{i.name}</span>
                      {i.hired ? <Badge tone="success">Already hired</Badge> : i.recommended ? <Badge tone="info">Recommended</Badge> : null}
                      {i.excluded_reason && <Badge tone="warning">Over budget</Badge>}
                      <span className="ml-auto text-xs text-muted">Est. {money(i.estimated_monthly_usd)} / month</span>
                    </div>
                    <div id={`why-${i.key}`} className="mt-1 text-xs text-muted">
                      {i.reasons.length ? <>Why: {i.reasons.join(" · ")}</> : "No signals in your profile point to this agent."}
                      {i.excluded_reason && <span className="block text-warning">{i.excluded_reason}</span>}
                    </div>
                  </div>
                </div>
              </label>
            );
          })}
        </fieldset>
      </div>
      <Card className="self-start lg:sticky lg:top-6">
        <CardHeader title={isRecommended ? "Recommended team" : "Custom team"} description={rec.method} />
        <div className="space-y-3 px-5 py-4 text-sm">
          <p><span className="text-2xl font-semibold">{selected.length}</span> agent{selected.length === 1 ? "" : "s"} selected</p>
          <p>Estimated {money(total)} / month</p>
          <p className={cn("text-xs", over ? "text-warning" : "text-muted")}>
            {over ? `Above your ${money(budget.amount, budget.currency)} monthly budget.` : budget.message}
          </p>
          {!isRecommended && recommended.length > 0 && (
            <button type="button" className="text-xs text-accent underline underline-offset-2" onClick={() => setSelected(recommended)}>Reset to the recommended team</button>
          )}
          {error && <Alert tone="danger">{error}</Alert>}
          {can("agent.hire") ? (
            <Button className="w-full" onClick={hire} loading={busy} disabled={!selected.length}><UserPlus /> Hire {selected.length || ""} selected</Button>
          ) : <p className="text-xs text-muted">Only owners and admins can hire agents.</p>}
          <p className="text-xs text-subtle">Hiring doesn&apos;t give an agent any access. Each one needs a configuration you approve.</p>
        </div>
      </Card>
    </div>
  );
}

export default function TeamPage() {
  const { data, error } = useOrgData<Recommendation>("/api/v1/agents/recommendation");
  return (
    <>
      <PageHeader eyebrow="AI workforce" title="Build your team"
        description="We recommend AI employees from your company profile, documents and budget — with the reason for each. Adjust the selection to build a custom team." />
      {error ? <ErrorState error={error} /> : !data ? <Spinner /> : data.items.every((i) => !i.recommended) && data.profile_gaps.length ? (
        <>
          <Alert tone="info" title="Nothing to recommend yet" className="mb-6">
            <Sparkles className="mr-1 inline size-4" aria-hidden />
            Your profile doesn&apos;t point to any agent yet. Add {data.profile_gaps.join(", ")} in{" "}
            <Link href="/app/onboarding" className="underline underline-offset-2">company setup</Link>, or choose agents yourself below.
          </Alert>
          <TeamBuilder key={data.recommended_keys.join()} rec={{ ...data, profile_gaps: [] }} />
        </>
      ) : <TeamBuilder key={data.recommended_keys.join()} rec={data} />}
    </>
  );
}
