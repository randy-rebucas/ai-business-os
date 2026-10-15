"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/display";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form";
import { api, ApiError } from "@/lib/api";
import { errorMessage } from "@/lib/forms";
import { useGlobalData } from "@/lib/hooks";
import type { CompanyProfile, DayHours, DayKey, SectionKey } from "@/lib/types";
import { cn } from "@/lib/utils";

export const STEP_FORM_ID = "step-form";

type FormProps = {
  profile: CompanyProfile;
  /** Sections this form covers: saving removes them from skipped_sections. */
  sections: SectionKey[];
  readOnly?: boolean;
  onSaved: (profile: CompanyProfile) => void;
};

async function saveProfile(profile: CompanyProfile, sections: SectionKey[], body: Record<string, unknown>) {
  const skipped = profile.skipped_sections.filter((s) => !sections.includes(s as SectionKey));
  return api<CompanyProfile>("/api/v1/company/profile", {
    method: "PATCH",
    org: true,
    body: { ...body, ...(skipped.length !== profile.skipped_sections.length ? { skipped_sections: skipped } : {}) },
  });
}

function useSave(props: FormProps) {
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const run = async (body: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    setFieldErrors({});
    try {
      props.onSaved(await saveProfile(props.profile, props.sections, body));
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors());
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return { error, fieldErrors, busy, run };
}

// ---- generic scalar fields -------------------------------------------------------------------------------------

export type ProfileFieldDef = {
  name: keyof CompanyProfile;
  label: string;
  kind: "text" | "textarea" | "select" | "number";
  options?: [string, string][];
  hint?: string;
  wide?: boolean;
  required?: boolean;
};

export function ProfileFieldsForm({ fields, ...props }: FormProps & { fields: ProfileFieldDef[] }) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((f) => [f.name, props.profile[f.name] == null ? "" : String(props.profile[f.name])])),
  );
  const { error, fieldErrors, run } = useSave(props);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const body: Record<string, unknown> = {};
    for (const f of fields) {
      const v = values[f.name].trim();
      body[f.name] = v === "" ? null : f.kind === "number" ? Number(v) : v;
    }
    void run(body);
  };

  return (
    <form id={STEP_FORM_ID} onSubmit={submit} noValidate className="space-y-4">
      {error && <Alert tone="danger">{error}</Alert>}
      <fieldset disabled={props.readOnly} className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => (
          <Field
            key={f.name}
            label={f.required ? f.label : `${f.label} (optional)`}
            hint={f.hint}
            error={fieldErrors[f.name]}
            className={cn((f.wide || f.kind === "textarea") && "sm:col-span-2")}
          >
            {(p) => {
              const common = { ...p, value: values[f.name], onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setValues((v) => ({ ...v, [f.name]: e.target.value })) };
              if (f.kind === "textarea") return <Textarea rows={4} {...common} />;
              if (f.kind === "select")
                return (
                  <Select {...common}>
                    <option value="">Not specified</option>
                    {f.options?.map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </Select>
                );
              return <Input type={f.kind === "number" ? "number" : "text"} {...common} />;
            }}
          </Field>
        ))}
      </fieldset>
    </form>
  );
}

// ---- operations: time zone, weekly hours, holidays ------------------------------------------------------------

const DAYS: [DayKey, string][] = [
  ["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"],
  ["sat", "Saturday"], ["sun", "Sunday"],
];
const DEFAULT_HOURS: DayHours = { open: "09:00", close: "17:00" };

export function OperationsForm(props: FormProps) {
  const { profile, readOnly } = props;
  const { data: zones } = useGlobalData<string[]>("/api/v1/company/timezones");
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const [timezone, setTimezone] = useState(profile.timezone ?? browserZone ?? "");
  const [schedule, setSchedule] = useState<Record<DayKey, DayHours | null>>(() => {
    const s = profile.operating_schedule;
    return Object.fromEntries(
      DAYS.map(([d]) => [d, s ? (s[d] ?? null) : ["sat", "sun"].includes(d) ? null : { ...DEFAULT_HOURS }]),
    ) as Record<DayKey, DayHours | null>;
  });
  const [holidays, setHolidays] = useState(profile.holidays);
  const { error, fieldErrors, run } = useSave(props);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    void run({
      timezone: timezone || null,
      operating_schedule: schedule,
      holidays: holidays.filter((h) => h.date && h.name.trim()),
    });
  };

  return (
    <form id={STEP_FORM_ID} onSubmit={submit} noValidate className="space-y-6">
      {error && <Alert tone="danger">{error}</Alert>}
      <fieldset disabled={readOnly} className="space-y-6">
        <Field label="Company time zone" error={fieldErrors.timezone} hint="Schedules, business hours and daily reports use this zone." className="max-w-sm">
          {(p) => (
            <Select {...p} value={timezone} onChange={(e) => setTimezone(e.target.value)}>
              <option value="">Not specified</option>
              {(zones ?? (timezone ? [timezone] : [])).map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </Select>
          )}
        </Field>

        <div>
          <p className="text-sm font-medium text-fg">Operating hours</p>
          <p className="mb-3 text-xs text-muted">AI employees in &quot;business hours&quot; mode only do routine work inside these hours.</p>
          <div className="divide-y divide-border rounded-md border border-border">
            {DAYS.map(([day, label]) => {
              const hours = schedule[day];
              return (
                <div key={day} className="flex flex-wrap items-center gap-3 px-3 py-2">
                  <Checkbox
                    label={label}
                    className="w-32"
                    checked={!!hours}
                    onChange={(e) => setSchedule((s) => ({ ...s, [day]: e.target.checked ? { ...DEFAULT_HOURS } : null }))}
                  />
                  {hours ? (
                    <div className="flex items-center gap-2 text-sm">
                      <Input type="time" aria-label={`${label} opens`} className="w-32" value={hours.open}
                        onChange={(e) => setSchedule((s) => ({ ...s, [day]: { ...hours, open: e.target.value } }))} />
                      <span className="text-muted">to</span>
                      <Input type="time" aria-label={`${label} closes`} className="w-32" value={hours.close}
                        onChange={(e) => setSchedule((s) => ({ ...s, [day]: { ...hours, close: e.target.value } }))} />
                    </div>
                  ) : (
                    <span className="text-sm text-subtle">Closed</span>
                  )}
                </div>
              );
            })}
          </div>
          {fieldErrors.close || fieldErrors.open ? <p className="mt-1 text-xs text-danger">{fieldErrors.close ?? fieldErrors.open}</p> : null}
        </div>

        <div>
          <p className="text-sm font-medium text-fg">Holidays</p>
          <p className="mb-3 text-xs text-muted">Days the business is closed. Routine work waits until the next working day.</p>
          <ul className="space-y-2">
            {holidays.map((h, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2">
                <Input type="date" aria-label="Holiday date" className="w-44" value={h.date}
                  onChange={(e) => setHolidays((hs) => hs.map((x, j) => (j === i ? { ...x, date: e.target.value } : x)))} />
                <Input aria-label="Holiday name" placeholder="Name" className="max-w-xs" value={h.name}
                  onChange={(e) => setHolidays((hs) => hs.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                <Button variant="ghost" size="icon" aria-label="Remove holiday" onClick={() => setHolidays((hs) => hs.filter((_, j) => j !== i))}>
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
          <Button variant="secondary" size="sm" className="mt-2" onClick={() => setHolidays((hs) => [...hs, { date: "", name: "" }])}>
            <Plus /> Add holiday
          </Button>
        </div>
      </fieldset>
    </form>
  );
}

// ---- reporting & budget ---------------------------------------------------------------------------------------

export function ReportingForm(props: FormProps) {
  const { profile, readOnly } = props;
  const [cadence, setCadence] = useState(profile.reporting_cadence ?? "");
  const [channels, setChannels] = useState({ in_app: true, email: false, sms: false, ...profile.notification_channels });
  const [budget, setBudget] = useState(profile.monthly_ai_budget ?? "");
  const [currency, setCurrency] = useState(profile.budget_currency);
  const { error, fieldErrors, run } = useSave(props);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    void run({
      reporting_cadence: cadence || null,
      notification_channels: channels,
      monthly_ai_budget: budget === "" ? null : budget,
      budget_currency: currency.trim().toUpperCase(),
    });
  };

  return (
    <form id={STEP_FORM_ID} onSubmit={submit} noValidate className="space-y-6">
      {error && <Alert tone="danger">{error}</Alert>}
      <fieldset disabled={readOnly} className="space-y-6">
        <Field label="How often do you want summaries?" error={fieldErrors.reporting_cadence} className="max-w-sm"
          hint="Every active AI employee still writes a daily activity report; this sets your digest.">
          {(p) => (
            <Select {...p} value={cadence} onChange={(e) => setCadence(e.target.value)}>
              <option value="">Not specified</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </Select>
          )}
        </Field>
        <div className="space-y-2">
          <p className="text-sm font-medium text-fg">Notification channels</p>
          <Checkbox label="In-app" checked={channels.in_app} onChange={(e) => setChannels((c) => ({ ...c, in_app: e.target.checked }))} />
          <Checkbox label="Email" checked={channels.email} onChange={(e) => setChannels((c) => ({ ...c, email: e.target.checked }))} />
          <Checkbox label="SMS" hint="For critical alerts only. Needs an SMS provider to be configured."
            checked={channels.sms} onChange={(e) => setChannels((c) => ({ ...c, sms: e.target.checked }))} />
        </div>
        <div className="grid max-w-md grid-cols-[1fr_7rem] gap-3">
          <Field label="Monthly AI workforce budget" error={fieldErrors.monthly_ai_budget}
            hint="A ceiling for model and execution costs across all AI employees.">
            {(p) => <Input {...p} type="number" min={0} step="0.01" inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)} />}
          </Field>
          <Field label="Currency" error={fieldErrors.budget_currency}>
            {(p) => <Input {...p} maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value)} />}
          </Field>
        </div>
      </fieldset>
    </form>
  );
}
