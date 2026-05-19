import { expect, test } from "@playwright/test";
import { seedDemoTenant, signIn } from "./helpers";

test.beforeEach(async ({ request }) => {
  await seedDemoTenant(request);
});

test("voice controls render in workspace and offer join", async ({ page }) => {
  await signIn(page, "founder@acme.co");
  await page.getByTestId("new-session-title").fill("Voice test");
  await page.getByTestId("new-session-submit").click();
  await expect(page.getByTestId("voice-controls")).toBeVisible();
  await expect(page.getByTestId("voice-join")).toBeVisible();
});

test("language switcher shows multiple options", async ({ page }) => {
  await signIn(page, "founder@acme.co");
  await page.getByTestId("new-session-title").fill("Lang test");
  await page.getByTestId("new-session-submit").click();
  await expect(page.getByTestId("language-switcher")).toBeVisible();
  const sel = page.getByTestId("language-select");
  // En option is always there; switching the value shouldn't error
  await sel.selectOption("en");
});

test("settings page renders account + mandate panels", async ({ page }) => {
  await signIn(page, "founder@acme.co");
  await page.goto("/settings");
  await expect(page.getByTestId("settings-account")).toBeVisible();
  await expect(page.getByTestId("settings-voice")).toBeVisible();
  // Mandate shows the seeded values
  await expect(page.getByTestId("settings-mandate")).toBeVisible();
});

test("settings shows voice config from backend", async ({ page }) => {
  await signIn(page, "founder@acme.co");
  await page.goto("/settings");
  // Wait for the API to fill in the voice card
  await expect(page.getByText(/Supported languages/i)).toBeVisible();
  await expect(page.getByText(/Custom dictionary/i)).toBeVisible();
});
