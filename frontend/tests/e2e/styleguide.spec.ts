import { expect, test } from "@playwright/test";

test("styleguide renders in light (default), toggles to dark, no h-scroll", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/styleguide");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText("Synthetic data").first()).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe("light");
  await page.screenshot({ path: "tests/e2e/styleguide-light.png", fullPage: true });
  await page.getByRole("button", { name: /switch to dark/i }).first().click();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe("dark");
  await page.screenshot({ path: "tests/e2e/styleguide-dark.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBeTruthy();
  await page.keyboard.press("/");
  await expect(page.getByPlaceholder(/jump to a po/i)).toBeFocused();
});
