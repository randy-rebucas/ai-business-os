import AxeBuilder from "@axe-core/playwright";
import { expect, type APIRequestContext, type Page } from "@playwright/test";

// Shared setup for the execution and reporting journeys (real stack, Celery worker).
export const HOURS = Object.fromEntries(["mon", "tue", "wed", "thu", "fri"].map((d) => [d, { open: "09:00", close: "17:00" }]));
export const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);

export async function axe(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const found = result.violations.flatMap((v) => v.nodes.map((n) => `${v.id}: ${n.target.join(" ")} — ${n.failureSummary}`));
  expect(found).toEqual([]);
}

export type Json = Record<string, unknown>;

export async function ok<T = Json>(p: Promise<{ ok(): boolean; text(): Promise<string>; json(): Promise<unknown> }>): Promise<T> {
  const r = await p;
  expect(r.ok(), await r.text()).toBeTruthy();
  return (await r.json()) as T;
}

/** Hire → generate → allow approved sending → approve → readiness suite on the worker → activate (observation). */
export async function activeFinance(request: APIRequestContext, headers: Record<string, string>) {
  const [inst] = await ok<{ id: string }[]>(request.post("/api/v1/agents", { headers, data: { definition_keys: ["finance"] } }));
  const gen = await ok<{ config: Json & { permissions: Json; job: { authorized_tools: string[] } }; tasks: Json[] }>(
    request.post(`/api/v1/agents/${inst.id}/config/generate`, { headers }));
  const tasks = gen.tasks.map((t) => {
    const { id: _id, position: _p, trigger_type, schedule, event, ...rest } = t;
    void _id; void _p;
    const task = { ...rest, trigger: { type: trigger_type, schedule, event } } as unknown as Json & { required_permissions: string[] };
    if (task.key === "review-outstanding-invoices") {
      task.required_permissions = [...task.required_permissions, "comms.external"];
      Object.assign(task, { approval_required: true, approval_reason: "Sending reminders needs approval." });
    }
    return task;
  });
  gen.config.permissions["comms.external"] = "approval_required";
  gen.config.job.authorized_tools.push("reminder.send");
  await ok(request.put(`/api/v1/agents/${inst.id}/config/draft`, { headers, data: { config: gen.config, tasks } }));
  const cfg = await ok<{ id: string; config_hash: string }>(request.post(`/api/v1/agents/${inst.id}/config/submit`, { headers }));
  await ok(request.post(`/api/v1/approvals/configurations/${cfg.id}/decide`, { headers,
    data: { decision: "approved", config_hash: cfg.config_hash } }));
  const run = await ok<{ id: string }>(request.post(`/api/v1/agents/${inst.id}/simulations`, { headers }));
  await expect.poll(async () => (await ok<{ status: string; passed: boolean }>(
    request.get(`/api/v1/simulations/runs/${run.id}`, { headers }))).passed, { timeout: 60_000 }).toBe(true);
  await ok(request.post(`/api/v1/agents/${inst.id}/activate`, { headers, data: { config_hash: cfg.config_hash } }));
  return inst.id;
}


/** Register a fresh workspace with a Manila company profile; returns tenant headers. */
export async function workspace(page: Page, tag: string) {
  const stamp = Date.now();
  const reg = await page.request.post("/api/v1/auth/register", {
    headers: { "X-Requested-With": "abos" },
    data: { email: `ceo+${tag}${stamp}@e2e.example.com`, password: "e2e-password-123", full_name: "Lea Cruz",
      organization_name: `Harbor ${tag} ${stamp}`, job_title: "CEO" },
  });
  expect(reg.status()).toBe(201);
  const headers = { "X-Requested-With": "abos", "X-Org-Id": (await reg.json()).memberships[0].organization.id };
  await ok(page.request.patch("/api/v1/company/profile", { headers, data: {
    timezone: "Asia/Manila", operating_schedule: HOURS, monthly_ai_budget: "300.00", budget_currency: "USD" } }));
  return headers;
}
