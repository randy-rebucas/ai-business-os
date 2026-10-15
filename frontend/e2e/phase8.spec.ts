import { expect, test } from "@playwright/test";

import { activeFinance, axe, day, logoPng, ok, workspace } from "./helpers";

// Phase 8: the platform's Annual Report identity and per-workspace branding. A food distributor uploads a saturated
// yellow logo — the hardest case for contrast — and the app derives an accessible accent from it, wears the logo in the
// shell, picks the "Works" type mood from the industry, and every page still passes axe. Screenshots: desktop + mobile.
const shots = "test-results/shots";

test("a workspace wears its own logo, accent and type mood, and stays accessible", async ({ page }) => {
  test.setTimeout(180_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const headers = await workspace(page, "b");
  await ok(page.request.patch("/api/v1/company/profile", { headers, data: { industry: "Food distribution" } }));
  await ok(page.request.post("/api/v1/business/invoices", { headers, data: {
    number: "INV-6001", customer_name: "Bayside Traders", customer_email: "ap@bayside.example.com", currency: "USD",
    issue_date: day(-70), due_date: day(-40), lines: [{ description: "Consulting", quantity: "2", unit_price: "2500.00" }] } }));
  const finance = await activeFinance(page.request, headers);
  const run = await ok<{ id: string }>(page.request.post("/api/v1/workflows", { headers,
    data: { agent_id: finance, task_key: "review-outstanding-invoices" } }));
  await expect.poll(async () => (await ok<{ status: string }>(page.request.get(`/api/v1/workflows/${run.id}`, { headers }))).status,
    { timeout: 60_000 }).toBe("awaiting_approval");

  // 1. Platform defaults before any branding: the platform accent and the industry's type mood.
  await page.goto("/app/settings#branding");
  const branding = page.locator("section").filter({ has: page.getByRole("heading", { name: "Branding" }) });
  await expect(branding.getByText("Matched from your industry (Food distribution).")).toBeVisible();
  await expect(branding.getByText("No logo yet")).toBeVisible();

  // 2. Upload a saturated yellow logo: the accent is derived and darkened for contrast, every check passes.
  await branding.getByLabel("Logo file").setInputFiles({ name: "harbor.png", mimeType: "image/png", buffer: logoPng([245, 196, 0]) });
  await expect(branding.getByText("Logo uploaded — accent derived from its colours.")).toBeVisible();
  await expect(branding.getByText("brand colour")).toBeVisible();
  await expect(branding.getByText(/^Links and focus use #/)).toBeVisible();
  await expect(branding.getByText(/^Buttons use your colour #f5c400 with dark text/)).toBeVisible();
  const checks = branding.getByRole("list").filter({ hasText: "Accent text and links on the page" });
  await expect(checks.locator("li")).toHaveCount(5);
  await expect(checks.locator(".text-danger")).toHaveCount(0);
  const api = await ok<{ accent: { light: string; brand: string }; mood: { key: string } }>(
    page.request.get("/api/v1/org/branding", { headers }));
  expect(api.mood.key).toBe("works");
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--brand-accent-light").trim()))
    .toBe(api.accent.light);
  await expect(page.getByRole("img", { name: /logo$/ }).first()).toBeVisible();  // the workspace logo in the rail
  await axe(page);
  await page.screenshot({ path: `${shots}/70-branding-settings.png`, fullPage: true });

  // 3. The Control Center in the workspace's brand: figures with note keys that open their notes.
  await page.goto("/app/control-center");
  await expect(page.getByText("Waiting for a decision")).toBeVisible();
  await page.getByRole("link", { name: "Note 2" }).click();
  await expect(page).toHaveURL(/#note-2$/);
  await expect(page.locator("#note-2")).toContainText("Held actions wait");
  const primary = await page.getByRole("link", { name: "Open the approval inbox" }).evaluate((el) => getComputedStyle(el).color);
  expect(primary).not.toBe("rgb(29, 107, 92)");  // the platform green was replaced by the derived accent
  await axe(page);
  await page.screenshot({ path: `${shots}/71-control-center-branded.png`, fullPage: true });

  // 4. The approval inbox focuses the held action.
  await page.goto("/app/approvals");
  await expect(page.getByRole("button", { name: "Approve this exact action" })).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/72-approvals-branded.png`, fullPage: true });

  // 5. An owner picks a colour and a type mood by hand; status colours never change.
  await page.goto("/app/settings#branding");
  await branding.getByLabel("Pick a colour").check();
  await branding.getByLabel("Hex").fill("#7b2d8e");
  await branding.getByLabel("Type mood").selectOption("market");
  await branding.getByRole("button", { name: "Save branding" }).click();
  await expect(branding.getByText("Branding saved.")).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.style.getPropertyValue("--mood-display").trim()))
    .toBe("var(--font-market-display)");
  // …and the display face really changed: headings now render in the Market mood's face.
  await expect.poll(() => page.getByRole("heading", { level: 1 }).evaluate((el) => getComputedStyle(el).fontFamily))
    .toContain("Bricolage");
  const success = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--color-success").trim());
  expect(success).toBe("#0e6b4f");
  await axe(page);

  // 6. Mobile: the rail collapses behind the menu; the readiness page shows the next step only.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/control-center");
  await expect(page.getByText("Waiting for a decision")).toBeVisible();
  await page.screenshot({ path: `${shots}/73-control-center-mobile.png`, fullPage: true });
  await page.goto(`/app/agents/${finance}/readiness`);
  await expect(page.getByRole("region", { name: "Next step" })).toContainText("Unlocks");
  await axe(page);
  await page.screenshot({ path: `${shots}/74-readiness-mobile.png`, fullPage: true });

  // 7. Public pages in the platform identity.
  await page.setViewportSize({ width: 1440, height: 900 });
  const anonContext = await page.context().browser()!.newContext({ baseURL: "http://localhost:3470" });
  const anon = await anonContext.newPage();
  await anon.goto("/");
  await expect(anon.getByRole("heading", { level: 1 })).toHaveText("AI employees you can audit.");
  await expect(anon.getByText(/Example daily report — illustrative figures/)).toBeVisible();
  await axe(anon);
  await anon.screenshot({ path: `${shots}/75-landing.png`, fullPage: true });
  await anon.setViewportSize({ width: 390, height: 844 });
  await anon.screenshot({ path: `${shots}/76-landing-mobile.png`, fullPage: true });
  await anon.setViewportSize({ width: 1440, height: 900 });
  await anon.goto("/login");
  await axe(anon);
  await anon.screenshot({ path: `${shots}/77-login.png`, fullPage: true });
  await anonContext.close();

  expect(consoleErrors).toEqual([]);
});
