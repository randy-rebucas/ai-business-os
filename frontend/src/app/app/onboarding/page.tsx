"use client";

import { Check, ChevronLeft, ChevronRight, Circle, CircleDashed, CircleDot } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useSWRConfig } from "swr";

import { STEP_FORM_ID } from "@/components/company/profile-forms";
import { STEPS, type StepDef } from "@/components/company/steps";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, ErrorState, PageHeader, ProgressBar, Spinner } from "@/components/ui/display";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useOrgData } from "@/lib/hooks";
import { SECTION_STATUS_LABEL, SECTION_TONE } from "@/lib/labels";
import { useSession } from "@/lib/session";
import type { CompanyProfile, Completeness, SectionStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

type StepState = "complete" | "partial" | "missing" | "skipped";

function stepState(step: StepDef, sections: SectionStatus[]): StepState {
  const mine = sections.filter((s) => step.sections.includes(s.key));
  if (!mine.length) return "missing";
  if (mine.every((s) => s.status === "complete")) return "complete";
  if (mine.every((s) => s.status === "skipped" || s.status === "complete")) return "skipped";
  if (mine.some((s) => s.status !== "missing")) return "partial";
  return "missing";
}

const STATE_ICON = { complete: Check, partial: CircleDot, missing: Circle, skipped: CircleDashed };

function Stepper({ current, sections, go }: { current: number; sections: SectionStatus[]; go: (i: number) => void }) {
  return (
    <nav aria-label="Setup steps">
      <ol className="space-y-0.5">
        {STEPS.map((step, i) => {
          const state = step.key === "review" ? null : stepState(step, sections);
          const Icon = state ? STATE_ICON[state] : ChevronRight;
          return (
            <li key={step.key}>
              <button
                type="button"
                onClick={() => go(i)}
                aria-current={i === current ? "step" : undefined}
                className={cn(
                  "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors",
                  i === current ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-surface hover:text-fg",
                )}
              >
                <Icon
                  aria-hidden
                  className={cn("size-4 shrink-0", state === "complete" && "text-success", state === "partial" && "text-warning")}
                />
                <span className="flex-1">{step.title}</span>
                {state && <span className="sr-only">({SECTION_STATUS_LABEL[state]})</span>}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function Review({ completeness, go }: { completeness: Completeness; go: (key: string) => void }) {
  return (
    <ul className="divide-y divide-border rounded-md border border-border">
      {completeness.sections.map((s) => {
        const step = STEPS.find((st) => st.sections.includes(s.key));
        return (
          <li key={s.key} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-fg">{s.label}</p>
              {s.missing.length > 0 && <p className="text-xs text-muted">Still needed: {s.missing.join(", ")}</p>}
            </div>
            <div className="flex items-center gap-3">
              <Badge tone={SECTION_TONE[s.status]}>{SECTION_STATUS_LABEL[s.status]}</Badge>
              {s.status !== "complete" && step && (
                <button type="button" onClick={() => go(step.key)} className="text-xs text-accent underline underline-offset-2">
                  Fill in
                </button>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function Wizard() {
  const router = useRouter();
  const params = useSearchParams();
  const { orgId, can } = useSession();
  const { mutate } = useSWRConfig();
  const readOnly = !can("company.write");
  const profileQ = useOrgData<CompanyProfile>("/api/v1/company/profile");
  const compQ = useOrgData<Completeness>("/api/v1/company/completeness");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const index = Math.max(0, STEPS.findIndex((s) => s.key === params.get("step")));
  const step = STEPS[index];
  const go = (i: number) => {
    setError(null);
    router.push(`/app/onboarding?step=${STEPS[Math.min(Math.max(i, 0), STEPS.length - 1)].key}`);
  };
  const goKey = (key: string) => go(STEPS.findIndex((s) => s.key === key));

  const refresh = async (profile?: CompanyProfile) => {
    await mutate(["/api/v1/company/profile", orgId], profile, { revalidate: !profile });
    await mutate(["/api/v1/company/completeness", orgId]);
  };

  const skip = async () => {
    const profile = profileQ.data;
    if (!profile) return;
    setBusy(true);
    try {
      const skipped = Array.from(new Set([...profile.skipped_sections, ...step.sections]));
      const updated = await api<CompanyProfile>("/api/v1/company/profile", {
        method: "PATCH", org: true, body: { skipped_sections: skipped },
      });
      await refresh(updated);
      go(index + 1);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    setBusy(true);
    try {
      await api("/api/v1/company/onboarding/complete", { method: "POST", org: true });
      await refresh();
      router.push("/app");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  if (profileQ.error || compQ.error) return <ErrorState error={profileQ.error ?? compQ.error} />;
  if (!profileQ.data || !compQ.data) return <Spinner label="Loading company setup" />;
  const profile = profileQ.data;
  const completeness = compQ.data;

  return (
    <>
      <PageHeader
        context={`Step ${index + 1} of ${STEPS.length}`}
        title="Set up your company"
        description="Your AI employees learn your business from this profile and the documents you add. Nothing here is mandatory — skip anything and come back later."
      />
      <div className="mb-6 max-w-md space-y-1.5">
        <div className="flex justify-between text-xs text-muted">
          <span>Profile completeness</span>
          <span>{completeness.percent}%</span>
        </div>
        <ProgressBar value={completeness.percent} label="Profile completeness" />
      </div>
      {readOnly && (
        <Alert tone="info" className="mb-6">
          You can view the company profile. Ask an owner, admin or manager to change it.
        </Alert>
      )}
      <div className="grid gap-6 lg:grid-cols-[15rem_1fr]">
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <Stepper current={index} sections={completeness.sections} go={go} />
        </aside>
        <Card>
          <div className="border-b border-border px-6 py-5">
            <h2 className="text-lg font-semibold text-fg">{step.title}</h2>
            <p className="mt-1 text-sm text-muted">{step.description}</p>
          </div>
          <div className="px-6 py-6">
            {step.key === "review" ? (
              <Review completeness={completeness} go={goKey} />
            ) : (
              // Keyed by profile version so forms re-initialise after saves instead of syncing state in effects.
              <div key={`${step.key}-${profile.updated_at}`}>
                {step.render({
                  profile,
                  readOnly,
                  onSaved: async (p) => {
                    await refresh(p);
                    go(index + 1);
                  },
                })}
              </div>
            )}
            {error && <Alert tone="danger" className="mt-4">{error}</Alert>}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-surface/50 px-6 py-4">
            <Button variant="ghost" onClick={() => go(index - 1)} disabled={index === 0}>
              <ChevronLeft /> Back
            </Button>
            {step.key === "review" ? (
              readOnly ? (
                <Link href="/app" className="text-sm text-accent underline underline-offset-2">Back to overview</Link>
              ) : (
                <Button onClick={finish} loading={busy}>
                  {profile.onboarding_completed_at ? "Done" : "Finish setup"}
                </Button>
              )
            ) : (
              <div className="flex gap-2">
                {!readOnly && (
                  <Button variant="secondary" onClick={skip} disabled={busy}>
                    Skip for now
                  </Button>
                )}
                {step.hasForm && !readOnly ? (
                  <Button type="submit" form={STEP_FORM_ID}>
                    Save &amp; continue <ChevronRight />
                  </Button>
                ) : (
                  <Button onClick={() => go(index + 1)}>
                    Continue <ChevronRight />
                  </Button>
                )}
              </div>
            )}
          </div>
        </Card>
      </div>
    </>
  );
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Wizard />
    </Suspense>
  );
}
