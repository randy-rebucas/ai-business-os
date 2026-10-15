"use client";

import { Pencil } from "lucide-react";

import { CollectionEditor, COLLECTIONS } from "@/components/company/collection-editor";
import { ButtonLink } from "@/components/ui/button";
import { Badge, Card, CardHeader, ErrorState, Meta, PageHeader, Spinner } from "@/components/ui/display";
import { useOrgData } from "@/lib/hooks";
import { SECTION_STATUS_LABEL, SECTION_TONE } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { CompanyProfile, Completeness, DayKey } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const DAY_LABEL: Record<DayKey, string> = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };

function Section({ title, step, status, children }: {
  title: string; step: string; status?: Completeness["sections"][number]; children: React.ReactNode;
}) {
  const { can } = useSession();
  return (
    <Card>
      <CardHeader
        title={title}
        description={status && status.status !== "complete" && status.missing.length ? `Missing: ${status.missing.join(", ")}` : undefined}
        action={
          <div className="flex items-center gap-2">
            {status && <Badge tone={SECTION_TONE[status.status]}>{SECTION_STATUS_LABEL[status.status]}</Badge>}
            {can("company.write") && (
              <ButtonLink href={`/app/onboarding?step=${step}`} size="sm" variant="ghost">
                <Pencil /> Edit
              </ButtonLink>
            )}
          </div>
        }
      />
      <div className="px-5 py-4">{children}</div>
    </Card>
  );
}

export default function CompanyPage() {
  const profileQ = useOrgData<CompanyProfile>("/api/v1/company/profile");
  const compQ = useOrgData<Completeness>("/api/v1/company/completeness");
  if (profileQ.error || compQ.error) return <ErrorState error={profileQ.error ?? compQ.error} />;
  if (!profileQ.data || !compQ.data) return <Spinner label="Loading company profile" />;
  const p = profileQ.data;
  const st = (key: string) => compQ.data!.sections.find((s) => s.key === key);
  const sched = p.operating_schedule;

  return (
    <>
      <PageHeader
        title={p.trading_name || p.company_name}
        description={`The approved description of your business. Last updated ${formatDate(p.updated_at)}.`}
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Basics" step="basics" status={st("basics")}>
          <dl>
            <Meta label="Company name">{p.company_name}</Meta>
            <Meta label="Legal name">{p.legal_name}</Meta>
            <Meta label="Trading name">{p.trading_name}</Meta>
            <Meta label="Industry">{p.industry}</Meta>
            <Meta label="Category">{p.business_category}</Meta>
          </dl>
          {p.description && <p className="mt-3 whitespace-pre-line text-sm text-fg/90">{p.description}</p>}
        </Section>
        <Section title="Customers" step="market" status={st("customers")}>
          <p className="whitespace-pre-line text-sm text-fg/90">{p.target_customers ?? <span className="text-muted">Not described yet.</span>}</p>
        </Section>
        <Section title="Products & services" step="market" status={st("offerings")}>
          <CollectionEditor def={COLLECTIONS.offerings} readOnly />
        </Section>
        <Section title="Locations" step="locations" status={st("locations")}>
          <CollectionEditor def={COLLECTIONS.locations} readOnly />
        </Section>
        <Section title="Organization" step="structure" status={st("structure")}>
          <dl>
            <Meta label="Size">{p.company_size}</Meta>
            <Meta label="Employees">{p.employee_count?.toLocaleString()}</Meta>
          </dl>
          {p.organization_structure && <p className="mt-3 whitespace-pre-line text-sm text-fg/90">{p.organization_structure}</p>}
          <h3 className="mb-2 mt-5 text-xs font-medium uppercase tracking-wide text-subtle">Departments</h3>
          <CollectionEditor def={COLLECTIONS.departments} readOnly />
          <h3 className="mb-2 mt-5 text-xs font-medium uppercase tracking-wide text-subtle">Job roles</h3>
          <CollectionEditor def={COLLECTIONS["job-roles"]} readOnly />
        </Section>
        <Section title="Objectives & KPIs" step="goals" status={st("objectives")}>
          <CollectionEditor def={COLLECTIONS.objectives} readOnly />
        </Section>
        <Section title="Operating hours" step="operations" status={st("operations")}>
          <dl>
            <Meta label="Time zone">{p.timezone}</Meta>
            {sched &&
              (Object.keys(DAY_LABEL) as DayKey[]).map((d) => (
                <Meta key={d} label={DAY_LABEL[d]}>{sched[d] ? `${sched[d]!.open} – ${sched[d]!.close}` : "Closed"}</Meta>
              ))}
          </dl>
          {p.holidays.length > 0 && (
            <p className="mt-3 text-sm text-muted">
              Holidays: {p.holidays.map((h) => `${h.name} (${formatDate(h.date)})`).join(", ")}
            </p>
          )}
        </Section>
        <Section title="Business processes" step="operations" status={st("processes")}>
          <CollectionEditor def={COLLECTIONS.processes} readOnly />
        </Section>
        <Section title="Software" step="systems" status={st("software")}>
          <CollectionEditor def={COLLECTIONS.software} readOnly />
        </Section>
        <Section title="Operational challenges" step="systems" status={st("challenges")}>
          <CollectionEditor def={COLLECTIONS.challenges} readOnly />
        </Section>
        <Section title="Reporting & budget" step="reporting" status={st("reporting")}>
          <dl>
            <Meta label="Cadence">{p.reporting_cadence}</Meta>
            <Meta label="Channels">
              {Object.entries(p.notification_channels).filter(([, on]) => on).map(([k]) => k.replace("_", "-")).join(", ") || null}
            </Meta>
            <Meta label="Monthly budget">{p.monthly_ai_budget != null ? `${p.monthly_ai_budget} ${p.budget_currency}` : null}</Meta>
          </dl>
        </Section>
      </div>
    </>
  );
}
