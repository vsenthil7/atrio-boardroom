import { expect, test } from "@playwright/test";
import { seedDemoTenant, signIn } from "./helpers";

/**
 * The single most important security property of the product: a treasury
 * action cannot be executed by a single user. Two distinct authorisers
 * must confirm it. We use two browser contexts to simulate two different
 * humans on two different machines.
 */
test("two-party authorisation: same user cannot self-second", async ({ browser, request }) => {
  await seedDemoTenant(request);

  // Founder: open session, propose a trade, first-authorise
  const founderCtx = await browser.newContext();
  const founder = await founderCtx.newPage();
  await signIn(founder, "founder@acme.co");
  await founder.getByTestId("new-session-title").fill("Trade");
  await founder.getByTestId("new-session-submit").click();
  const sessionUrl = founder.url();

  await founder.goto("/treasury");
  await founder.getByTestId("propose-session").selectOption({ index: 1 });
  await founder.getByTestId("propose-instrument").fill("SHV-xStock");
  await founder.getByTestId("propose-qty").fill("5");
  await founder.getByTestId("propose-submit").click();

  // Proposal appears as 'proposed'
  await expect(founder.getByTestId("proposal-row").first()).toBeVisible();
  await expect(founder.getByTestId("proposal-state").first()).toHaveText(/proposed/);

  // First authorisation — succeeds
  await founder.getByTestId("authorise-button").first().click();
  await expect(founder.getByTestId("proposal-state").first()).toHaveText(/first.authorised/i);

  // Same user attempts to second-authorise → button is hidden and the warning appears
  await expect(founder.getByTestId("two-party-warning")).toBeVisible();
  await expect(founder.getByTestId("authorise-button")).toBeHidden();

  // Now the CEO signs in (different browser context) and finishes the authorisation
  const ceoCtx = await browser.newContext();
  const ceo = await ceoCtx.newPage();
  await signIn(ceo, "ceo@acme.co");
  await ceo.goto("/treasury");

  await expect(ceo.getByTestId("proposal-row").first()).toBeVisible();
  await ceo.getByTestId("authorise-button").first().click();

  // State machine advances to executed
  await expect(ceo.getByTestId("proposal-state").first()).toHaveText(/executed/, {
    timeout: 10_000,
  });

  // Both browsers eventually agree (after a refetch on founder side)
  await founder.reload();
  await expect(founder.getByTestId("proposal-state").first()).toHaveText(/executed/);

  await founderCtx.close();
  await ceoCtx.close();

  void sessionUrl; // keep variable used
});

test("rejecting a proposal moves it to rejected state", async ({ browser, request }) => {
  await seedDemoTenant(request);
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await signIn(page, "founder@acme.co");

  await page.getByTestId("new-session-title").fill("Reject test");
  await page.getByTestId("new-session-submit").click();
  await page.goto("/treasury");
  await page.getByTestId("propose-session").selectOption({ index: 1 });
  await page.getByTestId("propose-instrument").fill("SHV-xStock");
  await page.getByTestId("propose-qty").fill("1");
  await page.getByTestId("propose-submit").click();

  await page.getByTestId("reject-button").first().click();
  await expect(page.getByTestId("proposal-state").first()).toHaveText(/rejected/);
  await ctx.close();
});

test("proposing a non-permitted instrument is rejected by the mandate", async ({
  browser,
  request,
}) => {
  await seedDemoTenant(request);
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await signIn(page, "founder@acme.co");
  await page.getByTestId("new-session-title").fill("Mandate test");
  await page.getByTestId("new-session-submit").click();
  await page.goto("/treasury");
  await page.getByTestId("propose-session").selectOption({ index: 1 });
  await page.getByTestId("propose-instrument").fill("BANNED-xStock");
  await page.getByTestId("propose-qty").fill("1");
  await page.getByTestId("propose-submit").click();
  await expect(page.getByTestId("propose-error")).toBeVisible();
  await ctx.close();
});
