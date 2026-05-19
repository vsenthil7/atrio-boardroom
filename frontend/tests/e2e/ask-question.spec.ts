import { expect, test } from "@playwright/test";
import { seedDemoTenant, signIn } from "./helpers";

test.beforeEach(async ({ request }) => {
  await seedDemoTenant(request);
});

test("creating a session and asking a question streams agent responses", async ({ page }) => {
  await signIn(page, "founder@acme.co");

  // Open a new session
  await page.getByTestId("new-session-title").fill("Should we hire 4 engineers?");
  await page.getByTestId("new-session-submit").click();
  await expect(page).toHaveURL(/\/sessions\/[a-f0-9-]+/);

  // Ask a question
  await page
    .getByTestId("turn-input")
    .fill("Given our runway, can we afford this hire?");
  await page.getByTestId("ask-submit").click();

  // The streaming indicator should appear
  await expect(page.getByTestId("streaming-indicator")).toBeVisible();

  // At least one streaming position should arrive
  await expect(page.getByTestId("streaming-position").first()).toBeVisible({
    timeout: 15_000,
  });

  // Eventually consensus card appears
  await expect(page.getByTestId("consensus-card")).toBeVisible({ timeout: 30_000 });

  // After stream ends, indicator goes away
  await expect(page.getByTestId("streaming-indicator")).toBeHidden({ timeout: 30_000 });

  // Multiple specialists rendered
  const positions = await page.getByTestId("streaming-position").count();
  expect(positions).toBeGreaterThanOrEqual(5);
});

test("single-mode (quick read) returns a single agent_done", async ({ page }) => {
  await signIn(page, "founder@acme.co");
  await page.getByTestId("new-session-title").fill("Quick read");
  await page.getByTestId("new-session-submit").click();
  await page.getByTestId("mode-select").selectOption("single");
  await page.getByTestId("turn-input").fill("Quick: do we proceed?");
  await page.getByTestId("ask-submit").click();
  await expect(page.getByTestId("consensus-card")).toBeVisible({ timeout: 30_000 });
  const positions = await page.getByTestId("streaming-position").count();
  expect(positions).toBe(1);
});
