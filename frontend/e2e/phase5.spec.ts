import { expect, test } from "@playwright/test";

import { activeFinance, axe, day, HOURS, ok } from "./helpers";

// Phase 5 journey against the real stack (runs execute on the Celery worker): invoices recorded → an active Finance
// agent (observation mode, sending allowed only with approval) runs its invoice review → reads records, drafts a
// reminder, escalates a discrepancy → the send waits in the approval inbox with its exact text → CEO approves →
// the run completes with every step in the evidence ledger. Then an ad-hoc request.
const stamp = Date.now();
const shots = "test-results/shots";

test("an active finance agent reviews invoices with evidence; its send waits for the CEO's approval", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const reg = await page.request.post("/api/v1/auth/register", {
    headers: { "X-Requested-With": "abos" },
    data: { email: `ceo+x${stamp}@e2e.example.com`, password: "e2e-password-123", full_name: "Lea Cruz",
      organization_name: `Harbor ${stamp}`, job_title: "CEO" },
  });
  expect(reg.status()).toBe(201);
  const headers = { "X-Requested-With": "abos", "X-Org-Id": (await reg.json()).memberships[0].organization.id };
  await ok(page.request.patch("/api/v1/company/profile", { headers, data: {
    timezone: "Asia/Manila", operating_schedule: HOURS, monthly_ai_budget: "300.00", budget_currency: "USD" } }));

  // 1. Records, entered through the validated business API (the form is exercised below).
  await ok(page.request.post("/api/v1/business/invoices", { headers, data: {
    number: "INV-7001", customer_name: "Bayside Traders", customer_email: "ap@bayside.example.com", currency: "USD",
    issue_date: day(-70), due_date: day(-40), lines: [{ description: "Consulting", quantity: "2", unit_price: "2500.00" }] } }));
  await ok(page.request.post("/api/v1/business/invoices", { headers, data: {
    number: "INV-7002", customer_name: "Northgate Ltd", currency: "USD", issue_date: day(-20), due_date: day(-5),
    source: "import", recorded_total: "12500.00",
    lines: [{ description: "A", unit_price: "10000.00" }, { description: "B", unit_price: "2000.00" }] } }));
  const finance = await activeFinance(page.request, headers);

  await page.goto("/app/records");
  await page.getByRole("button", { name: "Record invoice" }).waitFor();
  await page.getByLabel("Invoice number").fill("INV-7003");
  await page.getByLabel("Customer", { exact: true }).fill("Harbor Foods");
  await page.getByLabel("Due date").fill(day(10));
  await page.getByLabel("Line 1 description").fill("Supplies");
  await page.getByLabel("Unit price").fill("1250.50");
  await page.getByRole("button", { name: "Record invoice" }).click();
  const invoices = page.getByRole("table", { name: "Invoices" });
  await expect(invoices.getByRole("row").filter({ hasText: "INV-7003" }).getByText("1,250.50 USD").first()).toBeVisible();
  await expect(invoices.getByText("lines add up to 12000.00 but the total is 12500.00")).toBeVisible();
  await expect(page.getByText("18,250.50 USD")).toBeVisible();  // outstanding: 5000 + 12000 + 1250.50
  await axe(page);
  await page.screenshot({ path: `${shots}/40-records.png`, fullPage: true });

  // 2. Run the invoice review now; the worker executes it step by step.
  await page.goto("/app/tasks");
  const card = page.locator("li").filter({ hasText: "Finance and Accounting Agent" }).first();
  await card.locator("li").filter({ hasText: "Review outstanding invoices" }).getByRole("button", { name: "Run now" }).click();
  await expect(page).toHaveURL(/\/app\/tasks\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Awaiting approval").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Development mode")).toBeVisible();
  const ledger = page.getByRole("table", { name: "Tool executions" });
  await expect(ledger.getByRole("row").filter({ hasText: "invoices.read" }).getByText("Succeeded")).toBeVisible();
  await expect(ledger.getByRole("row").filter({ hasText: "reminder.draft" }).getByText("Succeeded")).toBeVisible();
  await expect(ledger.getByRole("row").filter({ hasText: "reminder.send" }).getByText("Held for approval")).toBeVisible();
  await expect(page.getByText("ap@bayside.example.com").first()).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/41-run-awaiting-approval.png`, fullPage: true });

  // 3. The approval inbox shows the exact action; approve it.
  await page.goto("/app/approvals");
  const action = page.locator("section").filter({ hasText: "Agent actions waiting" });
  await expect(action.getByText(/balance of 5000.00 USD/)).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/42-approval-inbox-action.png`, fullPage: true });
  await action.getByRole("button", { name: "Approve this exact action" }).click();
  await expect(page.getByText("No agent action is waiting.")).toBeVisible();
  await expect(page.getByRole("table", { name: "Approval decisions" }).getByText("Agent action")).toBeVisible();

  // 4. The run completes; every check passed and the reminder was handed to the (dev) mail adapter.
  await page.goto("/app/tasks");
  await page.getByRole("table", { name: "Task runs" }).getByRole("link", { name: "Review outstanding invoices" }).first().click();
  await expect(page.getByText("Completed", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Every figure comes from a tool result")).toBeVisible();
  await expect(ledger.getByRole("row").filter({ hasText: "reminder.send" }).getByText("Succeeded")).toBeVisible();
  await expect(ledger.getByRole("row").filter({ hasText: "escalate" }).getByText("Succeeded")).toBeVisible();  // INV-7002
  await expect(page.getByText(/Outstanding: 18250.50 USD/)).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/43-run-completed.png`, fullPage: true });

  await page.goto("/app/records");
  await page.getByRole("tab", { name: "Drafts" }).click();
  await expect(page.getByText("Payment reminder: invoice INV-7001")).toBeVisible();
  await expect(page.getByText("sent", { exact: true })).toBeVisible();
  await axe(page);

  // 5. An ad-hoc request, and the agent's activity history.
  await page.goto("/app/tasks");
  await page.getByLabel("Request").fill("Which receivables need attention this week?");
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.getByText("Completed", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/gathered evidence for/)).toBeVisible();
  await page.goto(`/app/agents/${finance}`);
  await page.getByRole("tab", { name: "Activity history" }).click();
  await expect(page.getByRole("table", { name: "Activity history" }).getByRole("row")).toHaveCount(3);
  await axe(page);
  await page.screenshot({ path: `${shots}/44-activity.png`, fullPage: true });

  expect(consoleErrors).toEqual([]);
});
