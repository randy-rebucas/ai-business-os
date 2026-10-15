"use client";

import { Check, ImageUp, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";
import { useSWRConfig } from "swr";

import { Mark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Alert, Badge, Card, CardHeader, ErrorState, Spinner } from "@/components/ui/display";
import { Field, Input, Select } from "@/components/ui/form";
import { api } from "@/lib/api";
import { useBranding, useLogoSrc } from "@/lib/branding";
import { MOOD_FONTS, type MoodKey } from "@/lib/fonts";
import { useAction } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import type { Branding } from "@/lib/types";
import { uploadWithProgress } from "@/lib/upload";
import { cn } from "@/lib/utils";

type Source = Branding["accent"]["source"];

const CHECKS: { key: keyof Branding["accent"]["contrast"]; label: string; needs: number }[] = [
  { key: "light_on_ground", label: "Accent text and links on the page", needs: 4.5 },
  { key: "text_on_light", label: "Button text on the accent", needs: 4.5 },
  { key: "dark_on_ground", label: "Accent in dark mode", needs: 4.5 },
  { key: "text_on_dark", label: "Button text in dark mode", needs: 4.5 },
  { key: "marker_on_rail", label: "Navigation marker on the green rail", needs: 3 },
];

function Swatch({ hex, label, selected }: { hex: string; label: string; selected?: boolean }) {
  return (
    <li className="flex items-center gap-2 text-xs">
      <span aria-hidden className={cn("size-6 shrink-0 rounded-sm border border-black/10", selected && "ring-2 ring-rule ring-offset-2 ring-offset-bg-2")}
        style={{ background: hex }} />
      <span className="ident text-muted">{hex}</span>
      <span className="text-subtle">{label}</span>
    </li>
  );
}

function Preview({ data }: { data: Branding }) {
  const fonts = MOOD_FONTS[data.mood.key as MoodKey] ?? MOOD_FONTS.report;
  const a = data.accent;
  return (
    <div className="overflow-hidden rounded-sm border border-border" aria-label="Preview of your workspace's brand">
      <div className="flex">
        <div className="w-40 shrink-0 bg-sidebar p-3 text-xs text-sidebar-fg">
          <p className="mb-2 font-semibold text-sidebar-muted">Navigation</p>
          <p className="flex items-center gap-2 rounded-sm bg-sidebar-2 px-2 py-1 font-semibold text-white">
            <span aria-hidden className="size-1.5" style={{ background: a.marker }} /> Control Center
          </p>
          <p className="flex items-center gap-2 px-2 py-1"><span className="size-1.5" /> Daily reports</p>
        </div>
        <div className="min-w-0 flex-1 bg-bg p-4" style={{ fontFamily: fonts.text }}>
          <p className="text-sm font-semibold">Tasks completed</p>
          <p style={{ fontFamily: fonts.display }} className="text-4xl font-extrabold leading-none tracking-tight">
            41<span className="align-super text-[0.32em] font-bold" style={{ color: a.note_light }}>1</span>
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
            <span className="rounded-sm px-3 py-1.5 font-semibold" style={{ background: a.fill_light, color: a.on_fill_light }}>Approve this action</span>
            <span className="font-semibold underline" style={{ color: a.light }}>Open the records</span>
            <Badge tone="success">Completed</Badge>
            <Badge tone="warning">Awaiting approval</Badge>
          </div>
        </div>
      </div>
    </div>
  );
}

type Act = ReturnType<typeof useAction>;

function Editor({ data, save, logo }: { data: Branding; save: Act; logo: Act }) {
  const { can, orgId, refresh } = useSession();
  const { mutate } = useSWRConfig();
  const editable = can("org.manage");
  const logoSrc = useLogoSrc(data.logo_url);
  const [source, setSource] = useState<Source>(data.accent.source);
  const [custom, setCustom] = useState(data.accent.source === "owner" ? data.accent.brand : (data.logo_brand ?? "#1d6b5c"));
  const [mood, setMood] = useState(data.mood_source === "owner" ? data.mood.key : "");
  const file = useRef<HTMLInputElement>(null);
  const reload = async (next?: Branding) => {
    await mutate(["/api/v1/org/branding", orgId], next, { revalidate: !next });
    await refresh();
  };
  const industryMood = data.mood_source === "industry" ? data.mood : null;

  const upload = (f: File) => logo.run(async () => {
    const form = new FormData();
    form.append("file", f);
    await reload(await uploadWithProgress<Branding>("/api/v1/org/branding/logo", form, () => {}).promise);
  }, "Logo uploaded — accent derived from its colours.");

  return (
    <div className="space-y-8 px-5 py-5">
      <section className="grid gap-6 md:grid-cols-[14rem_1fr]">
        <div>
          <h3 className="font-display text-sm font-bold">Logo</h3>
          <div className="mt-2 grid h-28 place-items-center rounded-sm border border-border bg-white p-3">
            {logoSrc
              // eslint-disable-next-line @next/next/no-img-element -- blob: URL of the re-encoded PNG
              ? <img src={logoSrc} alt="Current logo" className="max-h-full max-w-full object-contain" />
              : <span className="text-xs text-subtle">No logo yet</span>}
          </div>
          {editable && (
            <div className="mt-3 flex flex-wrap gap-2">
              <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" aria-label="Logo file"
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
              <Button variant="secondary" size="sm" loading={logo.busy} onClick={() => file.current?.click()}>
                <ImageUp /> {data.logo_url ? "Replace logo" : "Upload logo"}
              </Button>
              {data.logo_url && (
                <Button variant="ghost" size="sm" disabled={logo.busy} onClick={() => logo.run(async () => {
                  await reload(await api<Branding>("/api/v1/org/branding/logo", { method: "DELETE", org: true }));
                }, "Logo removed.")}><Trash2 /> Remove</Button>
              )}
            </div>
          )}
          <p className="mt-2 text-xs text-muted">PNG, JPEG or WebP, up to 1 MB. Stored re-encoded at 512 px.</p>
        </div>
        <div>
          <h3 className="font-display text-sm font-bold">Colours found in the logo</h3>
          {data.palette.length === 0 ? <p className="mt-2 text-sm text-muted">Upload a logo to extract its colours.</p> : (
            <ul className="mt-2 grid gap-2 sm:grid-cols-2">
              {data.palette.filter((p) => p.share >= 0.01).slice(0, 6).map((p) => (
                <Swatch key={p.hex} hex={p.hex} label={`${Math.round(p.share * 100)}% of the logo${p.hex === data.logo_brand ? " · brand colour" : ""}`}
                  selected={p.hex === data.logo_brand} />
              ))}
            </ul>
          )}
          {data.logo_url && !data.logo_brand && (
            <p className="mt-2 text-sm text-muted">This logo has no distinct colour (black, white or grey), so the platform accent is used. Pick a colour below to brand the workspace.</p>
          )}
          {logo.error && <Alert tone="danger" className="mt-3">{logo.error}</Alert>}
          {logo.done && <Alert tone="success" className="mt-3">{logo.done}</Alert>}
        </div>
      </section>

      <form className="space-y-6" onSubmit={(e) => {
        e.preventDefault();
        void save.run(async () => {
          await reload(await api<Branding>("/api/v1/org/branding", { method: "PUT", org: true, body: {
            accent_source: source, owner_accent: source === "owner" ? custom : null, mood: mood || null } }));
        }, "Branding saved.");
      }}>
        <fieldset disabled={!editable} className="grid gap-6 md:grid-cols-2">
          <div>
            <h3 id="accent-source" className="font-display text-sm font-bold">Accent colour</h3>
            <p className="mt-1 text-xs text-muted">Used for buttons, links, focus and the selected item. Status colours never change.</p>
            <div role="radiogroup" aria-labelledby="accent-source" className="mt-3 space-y-2 text-sm">
              {([["logo", "From the logo", !data.logo_brand], ["owner", "Pick a colour", false], ["platform", "Platform green", false]] as const)
                .map(([value, label, off]) => (
                  <label key={value} className={cn("flex items-center gap-2", off && "opacity-50")}>
                    <input type="radio" name="accent" value={value} checked={source === value} disabled={off}
                      onChange={() => setSource(value)} className="accent-accent" />
                    {label}
                  </label>
                ))}
            </div>
            {source === "owner" && (
              <div className="mt-3 flex items-end gap-2">
                <input type="color" aria-label="Accent colour picker" value={/^#[0-9a-f]{6}$/i.test(custom) ? custom : "#000000"}
                  onChange={(e) => setCustom(e.target.value)} className="h-9 w-12 cursor-pointer rounded-sm border border-border-strong bg-bg-2 p-1" />
                <Field label="Hex" className="w-32">
                  {(p) => <Input {...p} value={custom} onChange={(e) => setCustom(e.target.value.trim())} />}
                </Field>
              </div>
            )}
          </div>
          <div>
            <Field label="Type mood" hint={industryMood ? `Matched from your industry (${data.industry}).` : "Chosen by hand."}>
              {(p) => (
                <Select {...p} value={mood} onChange={(e) => setMood(e.target.value)}>
                  <option value="">Match our industry</option>
                  {data.moods.map((m) => <option key={m.key} value={m.key}>{m.label} — {m.display} / {m.text}</option>)}
                </Select>
              )}
            </Field>
            <p className="mt-2 text-xs text-muted">{data.mood.label}: {data.mood.description}.</p>
          </div>
        </fieldset>
        {editable && <Button type="submit" loading={save.busy}>Save branding</Button>}
        {save.error && <Alert tone="danger">{save.error}</Alert>}
        {save.done && <Alert tone="success">{save.done}</Alert>}
      </form>

      <section className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="font-display text-sm font-bold">Contrast checks</h3>
          <ul className="mt-2 divide-y divide-border text-sm">
            {CHECKS.map((c) => {
              const v = data.accent.contrast[c.key];
              const ok = v >= c.needs;
              return (
                <li key={c.key} className="flex items-center justify-between gap-3 py-2">
                  <span>{c.label}</span>
                  <span className={cn("inline-flex items-center gap-1 font-semibold", ok ? "text-success" : "text-danger")}>
                    {ok ? <Check className="size-3.5" aria-hidden /> : <X className="size-3.5" aria-hidden />}
                    {v.toFixed(1)}:1 <span className="font-normal text-subtle">needs {c.needs}:1</span>
                  </span>
                </li>
              );
            })}
          </ul>
          {data.accent.adjusted.length > 0 && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted">{data.accent.adjusted.map((n) => <li key={n}>{n}</li>)}</ul>
          )}
        </div>
        <div>
          <h3 className="font-display text-sm font-bold">Preview</h3>
          <div className="mt-2"><Preview data={data} /></div>
          <p className="mt-2 flex items-center gap-2 text-xs text-muted"><Mark className="size-4" /> The platform mark and status colours stay the same in every workspace.</p>
        </div>
      </section>
    </div>
  );
}

export function BrandingCard() {
  const { data, error } = useBranding();
  const save = useAction();
  const logo = useAction();
  return (
    <Card>
      <div id="branding" />
      <CardHeader title="Branding" description="Your logo, an accent drawn from it, and a typeface that suits your business." />
      {error ? <div className="p-5"><ErrorState error={error} /></div> : !data ? <Spinner /> : (
        <Editor key={JSON.stringify([data.accent, data.mood, data.logo_url])} data={data} save={save} logo={logo} />
      )}
    </Card>
  );
}
