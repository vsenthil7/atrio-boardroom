import { type APIRequestContext, type Page, expect } from "@playwright/test";

const API = "http://127.0.0.1:8000/api/v1";

/**
 * Seed two users into the in-memory test database via a dedicated test-only
 * endpoint. This is the simplest way to make the E2E suite deterministic
 * without exposing the DB to the frontend.
 *
 * In the actual deployment we'd use `seed_demo.py`; for the test backend we
 * use a small admin endpoint that's only enabled in `ATRIO_ENV=test|demo`.
 */
export async function seedDemoTenant(request: APIRequestContext): Promise<{
  founderEmail: string;
  secondEmail: string;
}> {
  const r = await request.post(`${API}/_test/seed-demo`);
  if (!r.ok()) {
    throw new Error(`seed failed: ${r.status()} ${await r.text()}`);
  }
  const body = await r.json();
  return { founderEmail: body.founder_email, secondEmail: body.second_email };
}

/** Sign in by requesting + consuming a magic link in dev/test mode. */
export async function signIn(page: Page, email: string): Promise<void> {
  await page.goto("/signin");
  await page.getByTestId("email-input").fill(email);
  await page.getByTestId("request-magic-link").click();
  // In test env the dev_token is auto-pasted into the textarea
  const tokenArea = page.getByTestId("token-input");
  await expect(tokenArea).toBeVisible();
  await expect(tokenArea).not.toHaveValue("");
  await page.getByTestId("consume-token").click();
  await expect(page).toHaveURL("/");
  await expect(page.getByTestId("user-email")).toHaveText(email);
}
