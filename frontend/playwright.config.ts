import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [["html", { open: "never" }], ["line"]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Backend + frontend dev servers will be started by `make e2e`
  webServer: process.env.E2E_NO_WEBSERVER
    ? undefined
    : [
        {
          command:
            "cd ../backend && ATRIO_ENV=test DATABASE_URL=sqlite+aiosqlite:///:memory: ATRIO_MOCK_INFERENCE=true MODEL_REGISTRY_PATH=../config/models/atrio.yaml PROMPTS_DIR=../prompts uvicorn app.main:create_app --factory --port 8000 --host 127.0.0.1",
          port: 8000,
          reuseExistingServer: !process.env.CI,
          timeout: 60_000,
        },
        {
          command: "npm run dev -- --host 127.0.0.1",
          port: 5173,
          reuseExistingServer: !process.env.CI,
          timeout: 60_000,
        },
      ],
});
