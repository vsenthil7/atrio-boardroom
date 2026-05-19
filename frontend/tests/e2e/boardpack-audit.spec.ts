import { expect, test } from "@playwright/test";
import { seedDemoTenant, signIn } from "./helpers";

test.beforeEach(async ({ request }) => {
  await seedDemoTenant(request);
});

test("boardpack PDF can be downloaded for an active session", async ({ page }) => {
  await signIn(page, "founder@acme.co");
  await page.getByTestId("new-session-title").fill("Pack test");
  await page.getByTestId("new-session-submit").click();
  // boardpack link points at the API — verify the URL via fetch through the page
  const url = await page
    .getByTestId("download-boardpack")
    .getAttribute("href");
  expect(url).toMatch(/\/api\/v1\/sessions\/[a-f0-9-]+\/boardpack\.pdf/);

  // Get auth token from localStorage so we can fetch with credentials
  const access = await page.evaluate(() => {
    const raw = localStorage.getItem("atrio-auth");
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.state?.accessToken;
  });
  expect(access).toBeTruthy();

  const r = await page.request.get(url!, {
    headers: { Authorization: `Bearer ${access}` },
  });
  expect(r.status()).toBe(200);
  expect(r.headers()["content-type"]).toContain("application/pdf");
  const body = await r.body();
  expect(body.subarray(0, 5).toString()).toBe("%PDF-");
});

test("audit page renders events and offers ZIP export", async ({ page }) => {
  await signIn(page, "founder@acme.co");
  await page.getByTestId("new-session-title").fill("Audit src");
  await page.getByTestId("new-session-submit").click();
  await page.getByTestId("close-session").click();

  await page.goto("/audit");
  await expect(page.getByTestId("audit-list")).toBeVisible();
  await expect(page.getByText(/session_closed/i)).toBeVisible();

  // Export button → ZIP via signed request
  const exportUrl = await page.getByTestId("audit-export").getAttribute("href");
  expect(exportUrl).toBe("/api/v1/audit/export");

  const access = await page.evaluate(() => {
    const raw = localStorage.getItem("atrio-auth");
    if (!raw) return null;
    return JSON.parse(raw)?.state?.accessToken;
  });
  const r = await page.request.get(exportUrl!, {
    headers: { Authorization: `Bearer ${access}` },
  });
  expect(r.status()).toBe(200);
  expect(r.headers()["content-type"]).toBe("application/zip");
});

test("close session shows closed state and prevents further turns", async ({ page }) => {
  await signIn(page, "founder@acme.co");
  await page.getByTestId("new-session-title").fill("Close test");
  await page.getByTestId("new-session-submit").click();
  await page.getByTestId("close-session").click();
  // Input is replaced by the "session is closed" message
  await expect(page.getByText(/session is closed/i)).toBeVisible();
});
