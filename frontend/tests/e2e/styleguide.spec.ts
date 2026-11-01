import { expect, test } from "@playwright/test";

test("styleguide renders in dark, toggles to light, no h-scroll", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/styleguide");
  await expect(page.getByRole("heading", { name: "Design system" })).toBeVisible();
  await expect(page.getByText("FourthMatch")).toBeVisible();
  await expect(page.getByText("Synthetic data")).toBeVisible();

  await page.screenshot({ path: "tests/e2e/styleguide-dark.png", fullPage: true });

  await page.getByRole("button", { name: /toggle theme|switch to light/i }).first().click();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe("light");
  await page.screenshot({ path: "tests/e2e/styleguide-light.png", fullPage: true });

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
  expect(overflow).toBeTruthy();

  // global search via "/" key
  await page.keyboard.press("/");
  await expect(page.getByLabel("Global search")).toBeFocused();
});
