"use client";

import { ArrowRight, Building2, ScrollText } from "lucide-react";
import Link from "next/link";

import { ButtonLink } from "@/components/ui/button";
import { Badge, Card, CardHeader, EmptyState, ErrorState, Meta, PageHeader, ProgressBar, Spinner } from "@/components/ui/display";
import { useOrgData } from "@/lib/hooks";
import { auditActionLabel, LIFECYCLE, ROLE_LABEL, SECTION_STATUS_LABEL, SECTION_TONE } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { AgentListItem, AuditEvent, CompanyProfile, Completeness, PendingApproval } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

function SetupCard({ completeness, profile }: { completeness: Completeness; profile: CompanyProfile }) {
  const open = completeness.sections.filter((s) => s.status !== "complete");
  return (
    <Card>
      <CardHeader
        title="Company setup"
        description={profile.onboarding_completed_at ? "Setup finished — keep the profile current as the business changes." : "Tell the platform about your business."}
        action={<ButtonLink href="/app/onboarding" size="sm" variant={profile.onboarding_completed_at ? "secondary" : "primary"}>
          {profile.onboarding_completed_at ? "Edit" : "Continue setup"} <ArrowRight />
        </ButtonLink>}
      />
      <div className="space-y-4 px-5 py-4">
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs text-muted">
            <span>{completeness.sections.length - open.length} of {completeness.sections.length} sections complete</span>
            <span>{completeness.percent}%</span>
          </div>
          <ProgressBar value={completeness.percent} label="Company profile completeness" />
        </div>
        {open.length > 0 ? (
          <ul className="grid gap-2 sm:grid-cols-2">
            {open.slice(0, 6).map((s) => (
              <li key={s.key} className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 rounded-md border border-border px-3 py-2 text-sm">
                <span>{s.label}</span>
                <Badge tone={SECTION_TONE[s.status]}>{SECTION_STATUS_LABEL[s.status]}</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-success">Every profile section is complete.</p>
        )}
        {open.length > 6 && <p className="text-xs text-muted">+{open.length - 6} more in setup</p>}
      </div>
    </Card>
  );
}

function CompanyCard({ profile }: { profile: CompanyProfile }) {
  return (
    <Card className="self-start">
      <CardHeader title="Company" action={<Link href="/app/company" className="text-xs text-accent underline-offset-2 hover:underline">View profile</Link>} />
      <dl className="px-5 py-3">
        <Meta label="Name">{profile.trading_name || profile.company_name}</Meta>
        <Meta label="Industry">{profile.industry}</Meta>
        <Meta label="Time zone">{profile.timezone}</Meta>
        <Meta label="Reporting">{profile.reporting_cadence ? `${profile.reporting_cadence[0].toUpperCase()}${profile.reporting_cadence.slice(1)}` : null}</Meta>
        <Meta label="AI budget">
          {profile.monthly_ai_budget != null
            ? `${Number(profile.monthly_ai_budget).toLocaleString(undefined, { minimumFractionDigits: 2 })} ${profile.budget_currency} / month`
            : null}
        </Meta>
      </dl>
    </Card>
  );
}

function WorkforceCard() {
  const { data: agents } = useOrgData<AgentListItem[]>("/api/v1/agents");
  const { data: pending } = useOrgData<PendingApproval[]>("/api/v1/approvals/pending");
  return (
    <Card className="self-start">
      <CardHeader title="AI workforce" action={<Link href="/app/agents" className="text-xs text-accent underline-offset-2 hover:underline">Directory</Link>} />
      <div className="space-y-3 px-5 py-4 text-sm">
        {!agents ? <Spinner /> : agents.length === 0 ? (
          <>
            <p className="text-muted">No AI employees hired yet.</p>
            <ButtonLink href="/app/agents/team" size="sm">See the recommended team <ArrowRight /></ButtonLink>
          </>
        ) : (
          <ul className="space-y-2">
            {agents.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2">
                <Link href={`/app/agents/${a.id}`} className="truncate hover:underline">{a.name}</Link>
                <Badge tone={LIFECYCLE[a.status].tone}>{LIFECYCLE[a.status].label}</Badge>
              </li>
            ))}
          </ul>
        )}
        {!!pending?.length && (
          <Link href="/app/approvals" className="block text-warning underline-offset-2 hover:underline">
            {pending.length} configuration{pending.length > 1 ? "s" : ""} waiting for approval
          </Link>
        )}
      </div>
    </Card>
  );
}

function ActivityCard() {
  const { data, error } = useOrgData<AuditEvent[]>("/api/v1/audit?limit=8");
  return (
    <Card>
      <CardHeader title="Recent activity" action={<Link href="/app/audit" className="text-xs text-accent underline-offset-2 hover:underline">Audit log</Link>} />
      <div className="px-5 py-3">
        {error ? (
          <ErrorState error={error} />
        ) : !data ? (
          <Spinner />
        ) : data.length === 0 ? (
          <p className="py-2 text-sm text-muted">No activity yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {data.map((e) => (
              <li key={e.id} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                <span className="min-w-0 truncate">
                  {auditActionLabel(e.action)}
                  {e.actor_name && <span className="text-muted"> · {e.actor_name}</span>}
                </span>
                <time dateTime={e.created_at} className="shrink-0 text-xs text-subtle">{formatDateTime(e.created_at)}</time>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

export default function OverviewPage() {
  const { me, membership, can } = useSession();
  const profileQ = useOrgData<CompanyProfile>(can("company.read") ? "/api/v1/company/profile" : null);
  const compQ = useOrgData<Completeness>(can("company.read") ? "/api/v1/company/completeness" : null);

  if (!membership) {
    return (
      <EmptyState icon={Building2} title="You are not part of a workspace">
        Ask a workspace owner to add you, or create your own workspace in Settings.
      </EmptyState>
    );
  }
  const firstName = me.user.full_name.split(" ")[0];
  return (
    <>
      <PageHeader
        eyebrow={membership.organization.name}
        title={`Good to see you, ${firstName}`}
        description={`You're signed in as ${[membership.job_title, ROLE_LABEL[membership.role]].filter(Boolean).join(" · ")}.`}
      />
      {profileQ.error || compQ.error ? (
        <ErrorState error={profileQ.error ?? compQ.error} />
      ) : !profileQ.data || !compQ.data ? (
        <Spinner />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <div className="space-y-6">
            <SetupCard completeness={compQ.data} profile={profileQ.data} />
            {can("audit.read") ? <ActivityCard /> : (
              <EmptyState icon={ScrollText} title="Activity is visible to admins">The audit log is limited to owners and admins.</EmptyState>
            )}
          </div>
          <div className="space-y-6">
            <CompanyCard profile={profileQ.data} />
            {can("agent.read") && <WorkforceCard />}
          </div>
        </div>
      )}
    </>
  );
}
