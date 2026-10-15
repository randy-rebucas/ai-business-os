import { expect, test } from "@playwright/test";

import { activeFinance, axe, day, ok, workspace } from "./helpers";

// Phase 6 journey against the real stack (Celery worker): an active Finance agent runs its invoice review → the
// approval request and the escalation reach the right people as notifications → preferences → today's daily report,
// built from the execution records → the Control Center with filters → usage & budgets → agent performance.
const shots = "test-results/shots";

test("reports, notifications, Control Center and usage come from execution records", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const headers = await workspace(page, "r");
  await ok(page.request.post("/api/v1/business/invoices", { headers, data: {
    number: "INV-8001", customer_name: "Bayside Traders", customer_email: "ap@bayside.example.com", currency: "USD",
    issue_date: day(-70), due_date: day(-40), lines: [{ description: "Consulting", quantity: "2", unit_price: "2500.00" }] } }));
  await ok(page.request.post("/api/v1/business/invoices", { headers, data: {
    number: "INV-8002", customer_name: "Northgate Ltd", currency: "USD", issue_date: day(-20), due_date: day(-5),
    source: "import", recorded_total: "12500.00",
    lines: [{ description: "A", unit_price: "10000.00" }, { description: "B", unit_price: "2000.00" }] } }));
  const finance = await activeFinance(page.request, headers);
  const run = await ok<{ id: string }>(page.request.post("/api/v1/workflows", { headers,
    data: { agent_id: finance, task_key: "review-outstanding-invoices" } }));
  await expect.poll(async () => (await ok<{ status: string }>(page.request.get(`/api/v1/workflows/${run.id}`, { headers }))).status,
    { timeout: 60_000 }).toBe("awaiting_approval");

  // 1. Notifications: the approval request and the escalation, with an unread badge in the navigation.
  await page.goto("/app/notifications");
  await expect(page.getByRole("link", { name: /Approval needed: Send approved payment reminders/ })).toBeVisible();
  await expect(page.getByLabel(/\d+ unread/).first()).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/50-notifications.png`, fullPage: true });
  await page.getByRole("tab", { name: "Preferences" }).click();
  await page.getByLabel("Email me immediately for").selectOption("warning");
  await page.getByLabel("Text me critical alerts").check();
  await page.getByLabel("Mobile number").fill("+639171234567");
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await expect(page.getByText(/development adapter: messages are stored, not sent/)).toBeVisible();
  await axe(page);

  // 2. Approve, then build today's report from the records.
  const [req] = await ok<{ id: string; params_hash: string }[]>(page.request.get("/api/v1/approvals/actions", { headers }));
  await ok(page.request.post(`/api/v1/approvals/actions/${req.id}/decide`, { headers,
    data: { decision: "approved", params_hash: req.params_hash } }));
  await expect.poll(async () => (await ok<{ status: string }>(page.request.get(`/api/v1/workflows/${run.id}`, { headers }))).status,
    { timeout: 60_000 }).toBe("completed");
  await page.goto("/app/notifications");
  await expect(page.getByRole("link", { name: /Finance and Accounting Agent escalated/ })).toBeVisible();  // INV-8002
  await page.goto("/app/reports");
  await page.getByRole("button", { name: /Build today's report/ }).click();
  await expect(page).toHaveURL(/\/app\/reports\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Built from records")).toBeVisible();
  await expect(page.getByText("So far (day not over)")).toBeVisible();
  await expect(page.getByRole("link", { name: "Review outstanding invoices" }).first()).toBeVisible();
  await expect(page.getByRole("table", { name: "Actions per tool" }).getByRole("row").filter({ hasText: "reminder.send" })).toBeVisible();
  await expect(page.getByText("No measurement source is connected for this KPI yet.").first()).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/51-daily-report.png`, fullPage: true });
  await page.goto("/app/reports");
  await expect(page.getByRole("table", { name: "Daily reports" }).getByText("So far")).toBeVisible();
  await axe(page);

  // 3. Control Center with filters.
  await page.goto("/app/control-center");
  const perf = page.getByRole("table", { name: "Agent performance" });
  await expect(perf.getByRole("row").filter({ hasText: "Finance and Accounting Agent" })).toBeVisible();
  await expect(page.getByText("Important escalations")).toBeVisible();
  await expect(page.getByRole("table", { name: "Recent runs" }).getByRole("link", { name: "Review outstanding invoices" })).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/52-control-center.png`, fullPage: true });
  await page.getByLabel("Run status").selectOption("failed");
  await expect(page.getByRole("table", { name: "Recent runs" })).toHaveCount(0);
  await page.getByLabel("Run status").selectOption("");
  await page.getByLabel("Priority").selectOption("high");
  await expect(page.getByRole("table", { name: "Recent runs" }).getByRole("row")).toHaveCount(2);  // header + review

  // 4. Usage & budgets, and the agent's own performance and reports.
  await page.goto("/app/usage");
  await expect(page.getByText("Development mode")).toBeVisible();
  await expect(page.getByRole("table", { name: "Agent budgets" }).getByText("60.00").first()).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/53-usage.png`, fullPage: true });
  await page.goto(`/app/agents/${finance}`);
  await page.getByRole("tab", { name: "Performance" }).click();
  await expect(page.getByText("Completion rate")).toBeVisible();
  await page.getByRole("tab", { name: "Reports" }).click();
  await expect(page.getByText("So far")).toBeVisible();
  await axe(page);

  expect(consoleErrors).toEqual([]);
});
