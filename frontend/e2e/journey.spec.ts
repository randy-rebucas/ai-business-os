import { expect, test } from "@playwright/test";

import { axe, day, ok } from "./helpers";

// Phase 7: the complete SPEC §9 journey in one run, through the UI, against the real stack (API + Celery worker):
//  1 create an organisation · 2 complete the company profile · 3 upload a business policy · 4 processed & indexed ·
//  5 select a Finance agent · 6 proposed job description & tasks · 7 CEO reviews & approves · 8 simulation runs ·
//  9 it passes the acceptance tests · 10 CEO activates · 11 authorised read-only finance task · 12 tool results &
//  evidence recorded · 13 daily report generated from those records · 14 report claims traced to evidence.
// Then the controls the MVP promises (pause → edit → re-approve → re-test → resume) and the Phase 7 data controls
// (export, scheduled deletion + cancel).
const stamp = Date.now();
const email = `ceo+j${stamp}@e2e.example.com`;
const password = "e2e-password-123";
const company = `Harbor Journey ${stamp}`;
const shots = "test-results/shots";
const POLICY = `# Credit Control Policy

## Overdue invoices
Invoices more than 30 days overdue get a written payment reminder.

## Discrepancies
Discrepancies between an invoice total and its lines must be escalated to the CEO before anyone contacts the customer.
`;
const RULE = "Discrepancies between an invoice total and its lines must be escalated";

test("SPEC §9: register → profile → policy → Finance agent → approve → test → activate → task → report → evidence", async ({ page }) => {
  test.setTimeout(240_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  // 1. A new user creates an organisation.
  await page.goto("/register");
  await page.getByLabel("Your name").fill("Maria Santos");
  await page.getByLabel("Company name").fill(company);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page).toHaveURL(/\/app\/onboarding/);

  // 2. The user completes the company profile (the wizard's required context: basics, hours, budget).
  await page.getByLabel("Industry (optional)").fill("Wholesale distribution");
  await page.getByRole("button", { name: "Save & continue" }).click();
  await expect(page.getByRole("heading", { name: "Products, services & customers" })).toBeVisible();
  await page.goto("/app/onboarding?step=operations");
  await page.getByLabel("Company time zone").selectOption("Asia/Manila");
  await page.getByRole("button", { name: "Save & continue" }).click();
  await expect(page.getByRole("heading", { name: "Software & challenges" })).toBeVisible();
  await page.goto("/app/onboarding?step=reporting");
  await page.getByLabel("Monthly AI workforce budget").fill("300");
  await page.getByLabel("Currency").fill("USD");
  await page.getByRole("button", { name: "Save & continue" }).click();
  await page.getByRole("button", { name: "Finish setup" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText("300.00 USD / month")).toBeVisible();
  const orgId = await page.evaluate(() => localStorage.getItem("abos.activeOrg"));
  const me = await ok<{ memberships: { organization: { id: string } }[] }>(page.request.get("/api/v1/auth/me"));
  const headers = { "X-Requested-With": "abos", "X-Org-Id": orgId ?? me.memberships[0].organization.id };

  // 3–4. Upload a business policy; the worker processes it; the CEO reviews and indexes it.
  await page.goto("/app/knowledge");
  await page.getByLabel("Choose files to upload").setInputFiles({ name: "credit-control.md", mimeType: "text/markdown", buffer: Buffer.from(POLICY) });
  const row = page.getByRole("row").filter({ hasText: "credit-control" });
  await expect(row.getByText("Awaiting review")).toBeVisible({ timeout: 30_000 });
  await row.getByRole("link", { name: "credit-control" }).click();
  await page.getByRole("button", { name: "Approve and index" }).click();
  await expect(page.getByText("Indexed", { exact: true })).toBeVisible();

  // The platform proposes business rules from the indexed policy; the CEO confirms one (only confirmed rules feed
  // agent configurations).
  await page.goto("/app/rules");
  await page.getByRole("button", { name: "Extract from knowledge" }).first().click();
  const rule = page.locator("section").filter({ hasText: RULE }).first();
  await expect(rule.getByText("Proposed rule")).toBeVisible();
  await rule.getByRole("button", { name: "Confirm as rule" }).click();
  await rule.getByRole("button", { name: "Confirm", exact: true }).click();
  await page.getByRole("button", { name: /^Confirmed \(/ }).click();
  await expect(page.getByText(RULE).first()).toBeVisible();

  // Business records the finance task will read (the record form itself is covered by the Phase 5 journey).
  await ok(page.request.post("/api/v1/business/invoices", { headers, data: {
    number: "INV-9001", customer_name: "Bayside Traders", customer_email: "ap@bayside.example.com", currency: "USD",
    issue_date: day(-70), due_date: day(-40), lines: [{ description: "Consulting", quantity: "2", unit_price: "2500.00" }] } }));
  await ok(page.request.post("/api/v1/business/invoices", { headers, data: {
    number: "INV-9002", customer_name: "Northgate Ltd", currency: "USD", issue_date: day(-20), due_date: day(-5),
    source: "import", recorded_total: "12500.00",
    lines: [{ description: "A", unit_price: "10000.00" }, { description: "B", unit_price: "2000.00" }] } }));

  // 5. The CEO selects a Finance agent.
  await page.goto("/app/agents/team");
  const finance = page.getByRole("checkbox", { name: /Finance and Accounting Agent/ });
  await expect(finance).toBeVisible();
  for (const box of await page.getByRole("checkbox").all()) {
    const isFinance = ((await box.getAttribute("aria-describedby")) ?? "").includes("finance");
    await box.setChecked(isFinance);
  }
  await expect(finance).toBeChecked();
  await page.getByRole("button", { name: "Hire 1 selected" }).click();
  await expect(page).toHaveURL(/\/app\/agents$/);

  // 6. The platform proposes a job description and tasks.
  await page.getByRole("link", { name: "Finance and Accounting Agent" }).click();
  await expect(page).toHaveURL(/\/app\/agents\/[0-9a-f-]{36}$/);
  const agentUrl = page.url();
  await page.getByRole("button", { name: "Generate job description & tasks" }).click();
  await page.getByRole("tab", { name: /Assigned tasks/ }).click();
  await expect(page.getByRole("heading", { name: "Review outstanding invoices" })).toBeVisible();
  await page.getByRole("tab", { name: "Job description" }).click();
  await expect(page.getByRole("heading", { name: "Mission" })).toBeVisible();
  await page.getByRole("tab", { name: "Responsibilities" }).click();
  await expect(page.getByText(RULE).first()).toBeVisible();  // the confirmed rule became an escalation policy

  // 7. The CEO reviews and approves the configuration.
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await page.getByRole("link", { name: "Review & decide" }).click();
  await expect(page.getByRole("heading", { name: /configuration v1/ })).toBeVisible();
  await page.getByRole("button", { name: "Approve configuration" }).click();
  await expect(page.getByText("Decision recorded.")).toBeVisible();

  // 8–9. The agent runs its simulation on the worker and passes the required acceptance tests.
  await page.goto(agentUrl);
  await page.getByRole("link", { name: "Readiness & deployment" }).click();
  await page.getByRole("button", { name: "Run readiness tests" }).click();
  await expect(page).toHaveURL(/\/app\/simulations\/runs\//);
  await expect(page.getByText("All required checks passed")).toBeVisible({ timeout: 60_000 });

  // 10. The CEO activates the agent (observation stage).
  await page.getByRole("link", { name: "Readiness & deployment" }).click();
  await page.getByRole("button", { name: "Activate in observation mode" }).click();
  await expect(page.getByText("Observation mode", { exact: true })).toBeVisible();

  // 11–12. The agent executes an authorised read-only finance task; tool results and evidence are recorded.
  await page.goto("/app/tasks");
  const card = page.locator("li").filter({ hasText: "Finance and Accounting Agent" }).first();
  await card.locator("li").filter({ hasText: "Review outstanding invoices" }).getByRole("button", { name: "Run now" }).click();
  await expect(page).toHaveURL(/\/app\/tasks\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Completed", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  const runUrl = page.url();
  const ledger = page.getByRole("table", { name: "Tool executions" });
  await expect(ledger.getByRole("row").filter({ hasText: "invoices.read" }).getByText("Succeeded")).toBeVisible();
  await expect(ledger.getByRole("row").filter({ has: page.getByText("escalate", { exact: true }) })
    .getByText("Succeeded")).toBeVisible();  // INV-9002's total disagrees with its lines
  await expect(page.getByText("Every figure comes from a tool result")).toBeVisible();
  await expect(page.getByText(/Outstanding: 17000.00 USD/)).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/60-journey-run.png`, fullPage: true });

  // The escalation reached the CEO as a notification.
  await page.goto("/app/notifications");
  await expect(page.getByRole("link", { name: /Finance and Accounting Agent escalated/ })).toBeVisible();

  // 13. The daily report is generated from those records.
  await page.goto("/app/reports");
  await page.getByRole("button", { name: /Build today's report/ }).click();
  await expect(page).toHaveURL(/\/app\/reports\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Built from records")).toBeVisible();
  const perTool = page.getByRole("table", { name: "Actions per tool" });
  await expect(perTool.getByRole("row").filter({ hasText: "invoices.read" })).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/61-journey-report.png`, fullPage: true });

  // 14. The CEO traces the report's claims to the supporting evidence: the completed task links to its run and
  // its write-once tool ledger.
  await page.getByRole("link", { name: "Review outstanding invoices" }).first().click();
  await expect(page).toHaveURL(runUrl);
  await expect(ledger.getByRole("row").filter({ hasText: "invoices.read" })).toBeVisible();
  await expect(page.getByText("Invoice INV-9001").first()).toBeVisible();

  // The CEO can pause, edit, re-approve and re-test.
  await page.goto(`${agentUrl}/readiness`);
  await page.getByRole("button", { name: "Pause agent" }).click();
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  await page.goto(`${agentUrl}/configure`);
  await page.getByLabel("Monthly budget (USD)").fill("45");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText(/Saved as version 2/)).toBeVisible();
  await page.goto(agentUrl);
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await page.getByRole("link", { name: "Review & decide" }).click();
  await expect(page.getByRole("heading", { name: /configuration v2/ })).toBeVisible();
  await page.getByRole("button", { name: "Approve configuration" }).click();
  await expect(page.getByText("Decision recorded.")).toBeVisible();
  await page.goto(`${agentUrl}/readiness`);
  await expect(page.getByText("Not run yet for this version")).toBeVisible();
  await page.getByRole("button", { name: "Run readiness tests" }).click();
  await expect(page.getByText("All required checks passed")).toBeVisible({ timeout: 60_000 });
  await page.getByRole("link", { name: "Readiness & deployment" }).click();
  await page.getByRole("button", { name: /Resume|Activate in observation mode/ }).click();
  await expect(page.getByRole("button", { name: "Pause agent" })).toBeVisible();
  await axe(page);

  // A material change (a new confirmed rule for Finance) flags the agent for re-testing in the Control Center.
  await ok(page.request.post("/api/v1/rules", { headers, data: { title: "Reminder cap",
    statement: "Send at most one reminder a week.", applies_to: ["finance"] } }));
  await page.goto("/app/control-center");
  await expect(page.getByRole("heading", { name: "Needs re-testing" })).toBeVisible();
  const flagged = page.getByRole("listitem").filter({ hasText: /No business-rule change since the run/ }).first();
  await expect(flagged.getByRole("link", { name: "Finance and Accounting Agent" })).toHaveAttribute("href", /\/readiness$/);
  await axe(page);

  // Data controls (Phase 7): export the workspace, schedule deletion, see the warning everywhere, cancel it.
  await page.goto("/app/settings");
  await page.getByRole("button", { name: "Export workspace data" }).click();
  const exports = page.getByRole("table", { name: "Workspace exports" });
  await expect(exports.getByText("ready")).toBeVisible({ timeout: 60_000 });
  const download = page.waitForEvent("download");
  await exports.getByRole("button", { name: "Download" }).click();
  expect((await download).suggestedFilename()).toMatch(/-export-\d{8}-\d{4}\.zip$/);
  await page.getByLabel(/Type the workspace name/).fill(company);
  await page.getByLabel("Your password").fill(password);
  await page.getByRole("button", { name: "Schedule deletion" }).click();
  await expect(page.getByText(/will be permanently deleted on/)).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "scheduled for permanent deletion" })).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/62-data-controls.png`, fullPage: true });
  await page.getByRole("button", { name: "Cancel deletion" }).click();
  await expect(page.getByText("Deletion cancelled.")).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "scheduled for permanent deletion" })).toHaveCount(0);
  const audit = await ok<{ action: string }[]>(page.request.get("/api/v1/audit?action=org.", { headers }));
  expect(audit.map((a) => a.action)).toEqual(expect.arrayContaining(
    ["org.export_requested", "org.export_downloaded", "org.deletion_scheduled", "org.deletion_cancelled"]));

  expect(consoleErrors).toEqual([]);
});
