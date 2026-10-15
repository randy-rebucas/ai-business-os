"use client";

import { CollectionEditor, COLLECTIONS } from "@/components/company/collection-editor";
import { OperationsForm, ProfileFieldsForm, ReportingForm } from "@/components/company/profile-forms";
import type { CompanyProfile, SectionKey } from "@/lib/types";

export type StepKey =
  | "basics" | "market" | "locations" | "structure" | "goals" | "operations" | "systems" | "reporting" | "review";

export type StepDef = {
  key: StepKey;
  title: string;
  description: string;
  sections: SectionKey[];
  /** Whether the step has a profile form submitted by the footer's primary button. */
  hasForm: boolean;
  render: (args: { profile: CompanyProfile; readOnly: boolean; onSaved: (p: CompanyProfile) => void }) => React.ReactNode;
};

function Sub({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 border-t border-border pt-6 first:border-t-0 first:pt-0">
      <div>
        <h3 className="text-sm font-semibold text-fg">{title}</h3>
        {hint && <p className="text-xs text-muted">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

const SIZES: [string, string][] = [
  ["1", "Just me"], ["2-10", "2–10 people"], ["11-50", "11–50 people"], ["51-200", "51–200 people"],
  ["201-1000", "201–1,000 people"], ["1000+", "More than 1,000"],
];

export const STEPS: StepDef[] = [
  {
    key: "basics",
    title: "Company basics",
    description: "Who you are. AI employees use this to introduce your business and frame their work.",
    sections: ["basics"],
    hasForm: true,
    render: ({ profile, readOnly, onSaved }) => (
      <ProfileFieldsForm profile={profile} readOnly={readOnly} onSaved={onSaved} sections={["basics"]} fields={[
        { name: "company_name", label: "Company name", kind: "text", required: true },
        { name: "trading_name", label: "Trading name", kind: "text" },
        { name: "legal_name", label: "Registered legal name", kind: "text" },
        { name: "industry", label: "Industry", kind: "text", hint: "e.g. Wholesale distribution, Dental clinic." },
        { name: "business_category", label: "Business category", kind: "text", hint: "e.g. B2B, retail, professional services." },
        { name: "description", label: "What the company does", kind: "textarea" },
      ]} />
    ),
  },
  {
    key: "market",
    title: "Products, services & customers",
    description: "What you sell and to whom. Prices here are notes only — authoritative price lists come from documents.",
    sections: ["customers", "offerings"],
    hasForm: true,
    render: ({ profile, readOnly, onSaved }) => (
      <div className="space-y-6">
        <Sub title="Target customers">
          <ProfileFieldsForm profile={profile} readOnly={readOnly} onSaved={onSaved} sections={["customers"]} fields={[
            { name: "target_customers", label: "Who are your customers?", kind: "textarea", hint: "Segments, industries, regions, typical order size." },
          ]} />
        </Sub>
        <Sub title="Products and services" hint="Saved as you add them.">
          <CollectionEditor def={COLLECTIONS.offerings} readOnly={readOnly} />
        </Sub>
      </div>
    ),
  },
  {
    key: "locations",
    title: "Locations & branches",
    description: "Where the business operates. A branch can have its own time zone.",
    sections: ["locations"],
    hasForm: false,
    render: ({ readOnly }) => <CollectionEditor def={COLLECTIONS.locations} readOnly={readOnly} />,
  },
  {
    key: "structure",
    title: "Size & organization",
    description: "Departments and existing roles tell the platform which AI employees would help and who they report to.",
    sections: ["structure", "roles"],
    hasForm: true,
    render: ({ profile, readOnly, onSaved }) => (
      <div className="space-y-6">
        <Sub title="Size">
          <ProfileFieldsForm profile={profile} readOnly={readOnly} onSaved={onSaved} sections={["structure"]} fields={[
            { name: "company_size", label: "Company size", kind: "select", options: SIZES },
            { name: "employee_count", label: "Number of employees", kind: "number" },
            { name: "organization_structure", label: "How the organization is structured", kind: "textarea", hint: "Reporting lines, who decides what." },
          ]} />
        </Sub>
        <Sub title="Departments" hint="Saved as you add them.">
          <CollectionEditor def={COLLECTIONS.departments} readOnly={readOnly} />
        </Sub>
        <Sub title="Existing job roles" hint="Human roles today — AI employees will work alongside them.">
          <CollectionEditor def={COLLECTIONS["job-roles"]} readOnly={readOnly} />
        </Sub>
      </div>
    ),
  },
  {
    key: "goals",
    title: "Objectives & KPIs",
    description: "What success looks like. AI employees report their work against these measures.",
    sections: ["objectives"],
    hasForm: false,
    render: ({ readOnly }) => <CollectionEditor def={COLLECTIONS.objectives} readOnly={readOnly} />,
  },
  {
    key: "operations",
    title: "Hours & processes",
    description: "When the business runs, and how work gets approved today.",
    sections: ["operations", "processes"],
    hasForm: true,
    render: ({ profile, readOnly, onSaved }) => (
      <div className="space-y-6">
        <Sub title="Time zone, hours and holidays">
          <OperationsForm profile={profile} readOnly={readOnly} onSaved={onSaved} sections={["operations"]} />
        </Sub>
        <Sub title="Business processes" hint="Saved as you add them. Include approval thresholds — they become candidate business rules later.">
          <CollectionEditor def={COLLECTIONS.processes} readOnly={readOnly} />
        </Sub>
      </div>
    ),
  },
  {
    key: "systems",
    title: "Software & challenges",
    description: "The tools you already use and what is slowing the business down.",
    sections: ["software", "challenges"],
    hasForm: false,
    render: ({ readOnly }) => (
      <div className="space-y-6">
        <Sub title="Current software">
          <CollectionEditor def={COLLECTIONS.software} readOnly={readOnly} />
        </Sub>
        <Sub title="Operational challenges">
          <CollectionEditor def={COLLECTIONS.challenges} readOnly={readOnly} />
        </Sub>
      </div>
    ),
  },
  {
    key: "reporting",
    title: "Reporting & budget",
    description: "How you want to hear from your AI workforce, and what you are willing to spend on it.",
    sections: ["reporting", "budget"],
    hasForm: true,
    render: ({ profile, readOnly, onSaved }) => (
      <ReportingForm profile={profile} readOnly={readOnly} onSaved={onSaved} sections={["reporting", "budget"]} />
    ),
  },
  {
    key: "review",
    title: "Review",
    description: "Anything still missing is fine — you can come back any time, and the platform will ask for context when it needs it.",
    sections: [],
    hasForm: false,
    render: () => null,
  },
];
