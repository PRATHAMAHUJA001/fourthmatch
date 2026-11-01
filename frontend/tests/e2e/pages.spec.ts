import { expect, test } from "@playwright/test";

const ROUTES = ["/", "/dock", "/cases", "/cases/2", "/cases/5", "/policy", "/analytics", "/eval", "/styleguide"];

for (const width of [1440, 390]) {
  for (const route of ROUTES) {
    test(`${route} @${width}: renders, no console errors, no horizontal scroll`, async ({ page }) => {
      const errors: string[] = [];
      page.on("console", (m) => { if (m.type() === "error") errors.push(`${m.text()} @ ${m.location().url}`); });
      page.on("pageerror", (e) => errors.push(String(e)));
      page.on("response", (r) => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
      await page.setViewportSize({ width, height: 900 });
      await page.goto(route);
      await expect(page.getByRole("heading").first()).toBeVisible();
      await page.waitForTimeout(600);
      expect(errors).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBeTruthy();
    });
  }
}

test("replay: pipeline runs to a verdict and links to the case", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/dock?replay=2");
  await expect(page.getByRole("link", { name: /open case/i })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("link", { name: /open case/i }).click();
  await expect(page).toHaveURL(/\/cases\/2$/);
});

test("command palette jumps to a case", async ({ page }) => {
  await page.goto("/dock");
  await expect(page.getByRole("heading", { name: "Receiving dock" })).toBeVisible();
  await page.keyboard.press("Control+k");
  await page.getByPlaceholder(/jump to a po/i).fill("Kaveri");
  await page.getByRole("option", { name: /FM\/PO\/26-27\/004/ }).click();
  await expect(page).toHaveURL(/\/cases\/4$/);
});

test("receiving queue: grid view persists and opens a case", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/dock");
  await page.getByRole("button", { name: /grid/i }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: /grid/i })).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("Receiving queue").getByRole("link").first().click();
  await expect(page).toHaveURL(/\/cases\/\d+$/);
});
