import AxeBuilder from "@axe-core/playwright";
import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { deflateSync } from "node:zlib";

/** A small PNG logo drawn in code (no binary fixture): a brand-coloured block with a dark wordmark bar on transparency. */
export function logoPng(rgb: [number, number, number], width = 200, height = 100): Buffer {
  const crcTable = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (buf: Buffer) => {
    let c = 0xffffffff;
    for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (type: string, data: Buffer) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type), data]);
    const sum = Buffer.alloc(4);
    sum.writeUInt32BE(crc(body));
    return Buffer.concat([len, body, sum]);
  };
  const rows: Buffer[] = [];
  for (let y = 0; y < height; y++) {
    const row = Buffer.alloc(1 + width * 4);
    for (let x = 0; x < width; x++) {
      const inBlock = x >= 10 && x < width - 10 && y >= 10 && y < height - 10;
      const inBar = x >= 30 && x < width - 30 && y >= 44 && y < 56;
      const px = inBar ? [17, 17, 17, 255] : inBlock ? [...rgb, 255] : [0, 0, 0, 0];
      row.set(px, 1 + x * 4);
    }
    rows.push(row);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr.set([8, 6, 0, 0, 0], 8); // 8-bit RGBA
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(Buffer.concat(rows))), chunk("IEND", Buffer.alloc(0))]);
}

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
