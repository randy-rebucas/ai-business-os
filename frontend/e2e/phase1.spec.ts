import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Phase 1 journey through the real UI: register → guided company setup → dashboard → persistence after re-login →
// member management → audit log. Creates a fresh workspace per run (unique email).
const stamp = Date.now();
const email = `ceo+${stamp}@e2e.example.com`;
const password = "e2e-password-123";
const shots = "test-results/shots";

async function axe(page: Page) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const found = result.violations.flatMap((v) => v.nodes.map((n) => `${v.id}: ${n.target.join(" ")} — ${n.failureSummary}`));
  expect(found).toEqual([]);
}

test("CEO onboards a company end to end", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  // Landing → register
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("AI employees");
  await page.getByRole("link", { name: "Create workspace" }).first().click();
  await expect(page).toHaveURL(/\/register/);
  await axe(page);
  await page.getByLabel("Your name").fill("Maria Santos");
  await page.getByLabel("Company name").fill(`Harbor Foods ${stamp}`);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create workspace" }).click();

  // Step 1: basics
  await expect(page).toHaveURL(/\/app\/onboarding/);
  await expect(page.getByRole("heading", { name: "Company basics" })).toBeVisible();
  await page.screenshot({ path: `${shots}/01-onboarding-basics.png`, fullPage: true });
  await page.getByLabel("Industry (optional)").fill("Food distribution");
  await page.getByLabel("Trading name (optional)").fill("Harbor Foods");
  await page.getByLabel("What the company does (optional)").fill("We supply restaurants with fresh produce.");
  await page.getByRole("button", { name: "Save & continue" }).click();

  // Step 2: market — form + an offering
  await expect(page.getByRole("heading", { name: "Products, services & customers" })).toBeVisible();
  await page.getByLabel("Who are your customers? (optional)").fill("Restaurants and hotels in Metro Manila");
  await page.getByRole("button", { name: "Add product or service" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Weekly produce box");
  await page.getByRole("button", { name: "Add product or service" }).last().click();
  await expect(page.getByText("Weekly produce box")).toBeVisible();
  await page.getByRole("button", { name: "Save & continue" }).click();

  // Step 3: locations — skip
  await expect(page.getByRole("heading", { name: "Locations & branches" })).toBeVisible();
  await page.getByRole("button", { name: "Skip for now" }).click();

  // Step 4: structure — department + role referencing it
  await expect(page.getByRole("heading", { name: "Size & organization" })).toBeVisible();
  await page.getByLabel("Company size (optional)").selectOption("11-50");
  await page.getByRole("button", { name: "Add department" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Finance");
  await page.getByRole("button", { name: "Add department" }).last().click();
  await expect(page.getByText("Finance", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Add job role" }).click();
  await page.getByLabel("Title", { exact: true }).fill("Accountant");
  await page.getByLabel("Department (optional)").selectOption({ label: "Finance" });
  await page.getByRole("button", { name: "Add job role" }).last().click();
  await expect(page.getByText("Accountant")).toBeVisible();
  await page.screenshot({ path: `${shots}/02-onboarding-structure.png`, fullPage: true });
  await page.getByRole("button", { name: "Save & continue" }).click();

  // Step 5: goals — continue without adding
  await expect(page.getByRole("heading", { name: "Objectives & KPIs" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();

  // Step 6: operations — time zone + hours (defaults Mon–Fri 9–5)
  await expect(page.getByRole("heading", { name: "Hours & processes" })).toBeVisible();
  await page.getByLabel("Company time zone").selectOption("Asia/Manila");
  await page.getByLabel("Saturday").check();
  await page.screenshot({ path: `${shots}/03-onboarding-operations.png`, fullPage: true });
  await page.getByRole("button", { name: "Save & continue" }).click();

  // Step 7: systems — continue; Step 8: reporting
  await expect(page.getByRole("heading", { name: "Software & challenges" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Reporting & budget" })).toBeVisible();
  await page.getByLabel("How often do you want summaries?").selectOption("daily");
  await page.getByLabel("Monthly AI workforce budget").fill("15000");
  await page.getByLabel("Currency").fill("PHP");
  await page.getByRole("button", { name: "Save & continue" }).click();

  // Review → finish
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  const locations = page.getByRole("listitem").filter({ hasText: "Locations & branches" });
  await expect(locations.getByText("Skipped for now", { exact: true })).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/04-onboarding-review.png`, fullPage: true });
  await page.getByRole("button", { name: "Finish setup" }).click();

  // Dashboard shows real data
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText("Good to see you, Maria")).toBeVisible();
  await expect(page.getByText("Food distribution")).toBeVisible();
  await expect(page.getByText("15,000.00 PHP / month")).toBeVisible();
  await expect(page.getByText("Onboarding completed")).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/05-dashboard.png`, fullPage: true });

  // Persistence across logout/login
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/company");
  await expect(page.getByRole("heading", { name: "Harbor Foods", level: 1 })).toBeVisible();
  await expect(page.getByText("Weekly produce box")).toBeVisible();
  await expect(page.getByText("Asia/Manila")).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/06-company.png`, fullPage: true });

  // Audit log lists the work
  await page.goto("/app/audit");
  await expect(page.getByText("Company profile updated").first()).toBeVisible();
  await expect(page.getByText("Departments created")).toBeVisible();
  await axe(page);
  await page.screenshot({ path: `${shots}/07-audit.png`, fullPage: true });

  // Settings renders with the owner as the only member
  await page.goto("/app/settings");
  await expect(page.getByRole("cell", { name: /^Maria Santos \(you\)/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove Maria Santos" })).toHaveCount(0);
  await axe(page);
  await page.screenshot({ path: `${shots}/08-settings.png`, fullPage: true });

  // Mobile layout
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/onboarding?step=operations");
  await expect(page.getByRole("heading", { name: "Hours & processes" })).toBeVisible();
  await page.screenshot({ path: `${shots}/09-mobile-onboarding.png`, fullPage: true });

  expect(consoleErrors).toEqual([]);
});

test("unauthenticated visitors are sent to login", async ({ page }) => {
  await page.goto("/app/company");
  await expect(page).toHaveURL(/\/login\?next=%2Fapp%2Fcompany/);
});
