import { expect, test } from "@playwright/test";

test.describe("smoke", () => {
  test("sign-in page renders", async ({ page }) => {
    await page.goto("/signin");
    // FIX 2026-05-19: use .first() because "Your" appears in heading + footer ("your AI boardroom").
    await expect(page.getByText("Your").first()).toBeVisible();
    await expect(page.getByText("AI Boardroom").first()).toBeVisible();
    await expect(page.getByTestId("email-input")).toBeVisible();
    await expect(page.getByTestId("request-magic-link")).toBeVisible();
  });

  test("unauthenticated users are redirected from /", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/signin/);
  });

  test("masthead is not rendered when signed out", async ({ page }) => {
    await page.goto("/signin");
    await expect(page.locator("text=Sessions").first()).toBeHidden();
  });
});
