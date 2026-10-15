import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Phase 3 journey against the real stack: company context + an approved SOP → extract & confirm a business rule →
// recommended team (customised to Finance only) → generate job description & tasks → edit → submit → CEO reviews the
// approval summary and approves → agent moves to Testing. Fresh workspace per run.
const stamp = Date.now();
const shots = "test-results/shots";
const HOURS = Object.fromEntries(["mon", "tue", "wed", "thu", "fri"].map((d) => [d, { open: "09:00", close: "17:00" }]));
const SOP = `# Refund Policy

## Automatic refunds
Customer support may approve refunds automatically up to 5,000 PHP per order when the order is less than 30 days old.

## Refunds above the limit
Refunds above 5,000 PHP require written approval from the Finance Manager before any money is returned.
`;

async function axe(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const found = result.violations.flatMap((v) => v.nodes.map((n) => `${v.id}: ${n.target.join(" ")} — ${n.failureSummary}`));
  expect(found).toEqual([]);
}

async function seedCompany(request: APIRequestContext, orgId: string) {
  const headers = { "X-Requested-With": "abos", "X-Org-Id": orgId };
  const ok = async (p: Promise<{ ok(): boolean; text(): Promise<string> }>) => {
    const r = await p;
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  await ok(request.patch("/api/v1/company/profile", { headers, data: {
    timezone: "Asia/Manila", operating_schedule: HOURS, monthly_ai_budget: "300.00", budget_currency: "USD",
    reporting_cadence: "daily", company_size: "11-50" } }));
  await ok(request.post("/api/v1/company/departments", { headers, data: { name: "Finance" } }));
  await ok(request.post("/api/v1/company/software", { headers, data: { name: "Xero", category: "accounting" } }));
  await ok(request.post("/api/v1/company/challenges", { headers, data: { title: "Customer invoices paid late", severity: "high" } }));
  const up = await request.post("/api/v1/documents", { headers, multipart: {
    file: { name: "refund-policy.md", mimeType: "text/markdown", buffer: Buffer.from(SOP) } } });
  expect(up.status()).toBe(201);
  const doc = await up.json();
  await expect.poll(async () => (await (await request.get(`/api/v1/documents/${doc.id}`, { headers })).json()).status,
    { timeout: 30_000 }).toBe("awaiting_review");
  await ok(request.post(`/api/v1/documents/${doc.id}/review`, { headers, data: { decision: "approve" } }));
}

test("CEO hires, configures and approves a Finance agent", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const reg = await page.request.post("/api/v1/auth/register", {
    headers: { "X-Requested-With": "abos" },
    data: { email: `ceo+a${stamp}@e2e.example.com`, password: "e2e-password-123", full_name: "Lea Cruz",
      organization_name: `Northwind ${stamp}`, job_title: "CEO" },
  });
  expect(reg.status()).toBe(201);
  await seedCompany(page.request, (await reg.json()).memberships[0].organization.id);

  // 1. Business rules: extract from the approved SOP, confirm the refund threshold.
  await page.goto("/app/rules");
  await page.getByRole("button", { name: "Extract from knowledge" }).first().click();
  await expect(page.getByText(/new items? from/)).toBeVisible();
  const rule = page.locator("section").filter({ hasText: "Refunds above 5,000 PHP require written approval" }).first();
  await expect(rule.getByText("Proposed rule")).toBeVisible();
  await expect(rule.getByText("5,000 PHP", { exact: true })).toBeVisible(); // threshold parsed from the quote
  await axe(page);
  await page.screenshot({ path: `${shots}/20-rules.png`, fullPage: true });
  await rule.getByRole("button", { name: "Confirm as rule" }).click();
  await rule.getByRole("button", { name: "Confirm", exact: true }).click();
  await page.getByRole("button", { name: /^Confirmed \(/ }).click();
  await expect(page.getByText("Refunds above 5,000 PHP require written approval").first()).toBeVisible();

  // 2. Recommended team, customised to Finance only.
  await page.goto("/app/agents/team");
  const finance = page.getByRole("checkbox", { name: /Finance and Accounting Agent/ });
  await expect(finance).toBeChecked();
  await expect(page.getByText(/Software: Xero \(accounting\)/).first()).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/21-team.png`, fullPage: true });
  for (const box of await page.getByRole("checkbox").all()) {
    const isFinance = (await box.getAttribute("aria-describedby")) === "why-finance";
    if (!isFinance && (await box.isChecked())) await box.uncheck();
  }
  await expect(page.getByRole("heading", { name: "Custom team" })).toBeVisible();
  await page.getByRole("button", { name: "Hire 1 selected" }).click();
  await expect(page).toHaveURL(/\/app\/agents$/);
  await expect(page.getByRole("row").filter({ hasText: "Finance and Accounting Agent" }).getByText("Selected")).toBeVisible();
  await axe(page);

  // 3. Generate the job description and tasks (labelled dev adapter).
  await page.getByRole("link", { name: "Finance and Accounting Agent" }).click();
  await page.getByRole("button", { name: "Generate job description & tasks" }).click();
  await expect(page.getByText("Development mode")).toBeVisible();
  await page.getByRole("tab", { name: /Assigned tasks/ }).click();
  await expect(page.getByRole("heading", { name: "Review outstanding invoices" })).toBeVisible();
  await expect(page.getByText("Weekdays at 16:00")).toBeVisible();
  await page.getByRole("tab", { name: "Job description" }).click();
  await expect(page.getByText("Refunds above 5,000 PHP require written approval from the Finance Manager").first()).toBeVisible();
  await page.getByRole("tab", { name: "Schedule" }).click();
  await expect(page.getByRole("table", { name: "Upcoming runs" })).toBeVisible();
  await axe(page);
  await page.getByRole("tab", { name: "Tools & permissions" }).click();
  await expect(page.getByRole("table", { name: "Permission scopes" })).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/22-agent-profile.png`, fullPage: true });

  // 4. Edit the draft.
  await page.getByRole("link", { name: "Edit configuration" }).click();
  await page.getByLabel("Monthly budget (USD)").fill("45");
  await axe(page);
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText("Saved as version 1 (draft).")).toBeVisible();
  await page.screenshot({ path: `${shots}/23-configure.png`, fullPage: true });
  await page.getByRole("link", { name: "Back to agent" }).click();

  // 5. Submit, then the CEO reviews the approval summary and approves.
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByText("Waiting for the CEO's approval")).toBeVisible();
  await page.getByRole("link", { name: "Review & decide" }).click();
  await expect(page.getByRole("heading", { name: /configuration v1/ })).toBeVisible();
  await expect(page.getByText("45.00 USD / month")).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/24-approval-summary.png`, fullPage: true });
  await page.getByRole("button", { name: "Approve configuration" }).click();
  await expect(page.getByText("Decision recorded.")).toBeVisible();

  await page.goto("/app/approvals");
  await expect(page.getByRole("cell", { name: /Approved/ }).first()).toBeVisible();
  await axe(page);
  await page.getByRole("link", { name: "Finance and Accounting Agent" }).click();
  await expect(page.getByText("Configuration approved")).toBeVisible();
  await expect(page.getByText("Cannot execute work")).toBeVisible();
  await page.getByRole("tab", { name: "Configuration versions" }).click();
  await expect(page.getByText("Approved version")).toBeVisible();

  // 6. Catalog shows the hired agent's state.
  await page.goto("/app/agents/catalog");
  await expect(page.locator("section").filter({ hasText: "Finance and Accounting Agent" }).getByText("Testing")).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/25-catalog.png`, fullPage: true });

  expect(consoleErrors).toEqual([]);
});
