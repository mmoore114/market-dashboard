import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./browser",
  testMatch: process.env.APERTURE_UX_FIXTURE
    ? "workstation.spec.ts"
    : "research.spec.ts",
  workers: 1,
  timeout: 60000,
  outputDir: process.env.APERTURE_UX_RESULTS || "test-results/research",
  use: {
    baseURL: process.env.APERTURE_UX_URL || "http://127.0.0.1:5174",
    reducedMotion: "reduce",
  },
});
