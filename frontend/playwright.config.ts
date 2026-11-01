import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  use: { baseURL: "http://localhost:5173" },
  webServer: {
    command: "node scripts/copy-demo-assets.mjs && VITE_MOCK=1 npx vite --port 5173",
    url: "http://localhost:5173/styleguide",
    reuseExistingServer: true,
    timeout: 30_000,
  },
  projects: [{
    name: "chromium",
    use: {
      ...devices["Desktop Chrome"],
      // Optional: point at a preinstalled Chromium (e.g. CI containers) without reinstalling browsers.
      launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
    },
  }],
});
