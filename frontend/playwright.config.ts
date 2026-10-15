import { defineConfig, devices } from "@playwright/test";

// Runs against the already-running local stack (next start :3470 → uvicorn :8470).
// Uses the installed Chrome (channel "chrome"), so no browser download is needed: npm run test:e2e
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.ABOS_WEB ?? "http://localhost:3470",
    channel: "chrome",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
});
