import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Phase 4 journey against the real stack (runs execute on the Celery worker): an approved Finance agent is tested in
// the sandbox → passes → becomes ready → CEO activates it in observation mode → pause/resume. A deliberately unsafe
// Sales configuration fails its security checks and is fixed with an applied suggestion.
const stamp = Date.now();
const shots = "test-results/shots";
const HOURS = Object.fromEntries(["mon", "tue", "wed", "thu", "fri"].map((d) => [d, { open: "09:00", close: "17:00" }]));

async function axe(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const found = result.violations.flatMap((v) => v.nodes.map((n) => `${v.id}: ${n.target.join(" ")} — ${n.failureSummary}`));
  expect(found).toEqual([]);
}

type Cfg = { id: string; config_hash: string; config: Record<string, unknown> & { permissions: Record<string, string> };
  tasks: Record<string, unknown>[] };

async function approvedAgent(request: APIRequestContext, headers: Record<string, string>, key: string,
  edit?: (body: { config: Cfg["config"]; tasks: Record<string, unknown>[] }) => void) {
  const ok = async <T,>(p: Promise<{ ok(): boolean; text(): Promise<string>; json(): Promise<T> }>) => {
    const r = await p;
    expect(r.ok(), await r.text()).toBeTruthy();
    return r.json();
  };
  const [inst] = await ok<{ id: string }[]>(request.post("/api/v1/agents", { headers, data: { definition_keys: [key] } }));
  let cfg = await ok<Cfg>(request.post(`/api/v1/agents/${inst.id}/config/generate`, { headers }));
  if (edit) {
    const tasks = cfg.tasks.map((t) => {
      const { id: _id, position: _p, trigger_type, schedule, event, ...rest } = t as Record<string, unknown>;
      void _id; void _p;
      return { ...rest, trigger: { type: trigger_type, schedule, event } };
    });
    const body = { config: cfg.config, tasks };
    edit(body);
    cfg = await ok<Cfg>(request.put(`/api/v1/agents/${inst.id}/config/draft`, { headers, data: body }));
  }
  cfg = await ok<Cfg>(request.post(`/api/v1/agents/${inst.id}/config/submit`, { headers }));
  await ok(request.post(`/api/v1/approvals/configurations/${cfg.id}/decide`, { headers,
    data: { decision: "approved", config_hash: cfg.config_hash } }));
  return inst.id;
}

test("readiness testing, activation in observation mode, and a failing configuration fixed", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const reg = await page.request.post("/api/v1/auth/register", {
    headers: { "X-Requested-With": "abos" },
    data: { email: `ceo+s${stamp}@e2e.example.com`, password: "e2e-password-123", full_name: "Lea Cruz",
      organization_name: `Harbor ${stamp}`, job_title: "CEO" },
  });
  expect(reg.status()).toBe(201);
  const headers = { "X-Requested-With": "abos", "X-Org-Id": (await reg.json()).memberships[0].organization.id };
  expect((await page.request.patch("/api/v1/company/profile", { headers, data: {
    timezone: "Asia/Manila", operating_schedule: HOURS, monthly_ai_budget: "300.00", budget_currency: "USD" } })).ok()).toBeTruthy();
  const finance = await approvedAgent(page.request, headers, "finance");

  // 1. Not ready until tested; run the suite on the real worker.
  await page.goto(`/app/agents/${finance}`);
  await page.getByRole("link", { name: "Readiness & deployment" }).click();
  await expect(page.getByText("Not run yet for this version")).toBeVisible();
  await axe(page);
  await page.getByRole("button", { name: "Run readiness tests" }).click();
  await expect(page).toHaveURL(/\/app\/simulations\/runs\//);
  await expect(page.getByText("All required checks passed")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Development mode")).toBeVisible();
  await expect(page.getByRole("table", { name: "Scores by dimension" })).toBeVisible();
  await page.getByText("Review outstanding invoices", { exact: true }).click();
  const review = page.getByRole("table", { name: "Actions in Review outstanding invoices" });
  await expect(review.getByRole("row").filter({ hasText: "reminder.send" }).getByText("Blocked")).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/30-run-passed.png`, fullPage: true });

  // 2. Ready → activate in observation mode → pause → resume.
  await page.getByRole("link", { name: "Readiness & deployment" }).click();
  await expect(page.getByText("Ready for deployment").first()).toBeVisible();
  await page.getByRole("button", { name: "Activate in observation mode" }).click();
  await expect(page.getByText("Observation mode", { exact: true })).toBeVisible();
  await expect(page.getByText("Active", { exact: true }).first()).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/31-activated.png`, fullPage: true });
  await page.getByLabel("Reason (optional)").fill("Month-end freeze");
  await page.getByRole("button", { name: "Pause agent" }).click();
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  await page.getByRole("button", { name: "Resume" }).click();
  await expect(page.getByRole("button", { name: "Pause agent" })).toBeVisible();

  // 3. An unsafe Sales configuration fails its security checks; apply the suggested fix.
  const sales = await approvedAgent(page.request, headers, "sales", (body) => {
    body.config.permissions = { ...body.config.permissions, "comms.external": "auto", "records.modify": "auto" };
    for (const t of body.tasks) { t.approval_required = false; t.approval_reason = null; }
  });
  await page.goto(`/app/agents/${sales}/readiness`);
  await page.getByRole("button", { name: "Run readiness tests" }).click();
  await expect(page.getByText("Not ready", { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/mandatory security or authorisation check/)).toBeVisible();
  const card = page.locator("section").filter({ hasText: "An action that needs a person's approval" }).last();
  await expect(card.getByText("What failed")).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/32-run-failed.png`, fullPage: true });
  await card.getByRole("button", { name: "Apply" }).first().click();
  await expect(page.getByText(/Applied as configuration version 2/)).toBeVisible();

  // 4. Simulation center: runs + scenario library.
  await page.goto("/app/simulations");
  await expect(page.getByRole("table", { name: "Simulation runs" }).getByRole("row")).toHaveCount(3);
  await expect(page.getByText(/of 14 categories/)).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/33-simulation-center.png`, fullPage: true });

  expect(consoleErrors).toEqual([]);
});
