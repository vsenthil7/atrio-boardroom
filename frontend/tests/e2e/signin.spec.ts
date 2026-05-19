import { expect, test } from "@playwright/test";
import { seedDemoTenant, signIn } from "./helpers";

test.beforeEach(async ({ request }) => {
  await seedDemoTenant(request);
});

test("magic-link sign-in flow", async ({ page }) => {
  await signIn(page, "founder@acme.co");
  await expect(page.getByText("Sessions").first()).toBeVisible();
  await expect(page.getByTestId("user-email")).toHaveText("founder@acme.co");
});

test("invalid token shows error", async ({ page }) => {
  await page.goto("/signin");
  await page.getByTestId("email-input").fill("founder@acme.co");
  await page.getByTestId("request-magic-link").click();
  await page.getByTestId("token-input").fill("not.a.real.jwt");
  await page.getByTestId("consume-token").click();
  await expect(page.getByTestId("signin-error")).toBeVisible();
});

test("sign-out returns to /signin", async ({ page }) => {
  await signIn(page, "founder@acme.co");
  await page.getByTestId("signout").click();
  await expect(page).toHaveURL(/\/signin/);
});
