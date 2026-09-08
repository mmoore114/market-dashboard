import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./browser",
  testMatch: process.env.APERTURE_CURRENT_COHORT
    ? "current-cohort.spec.ts"
    : process.env.APERTURE_GROUPS_SMOKE
      ? "groups.spec.ts"
      : process.env.APERTURE_ENGINE_COMPARISON
        ? "comparison.spec.ts"
        : process.env.APERTURE_REAL_SNAPSHOT
          ? "bootstrap.spec.ts"
          : "workstation.spec.ts",
  workers: 1,
  use: { baseURL: "http://127.0.0.1:5173", reducedMotion: "reduce" },
  webServer: [
    {
      command:
        "cd .. && .venv/bin/python -m uvicorn api.main:create_app --factory --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/api/v1/health",
      env: process.env.APERTURE_REAL_SNAPSHOT
        ? {
            APERTURE_MODE: "LOCAL_SNAPSHOT",
            APERTURE_SNAPSHOT_PATH: process.env.APERTURE_REAL_SNAPSHOT,
          }
        : {
            APERTURE_MODE: "FIXTURE",
            APERTURE_FIXTURE_SCENARIO: "GREEN",
            APERTURE_FIXTURE_POLICY:
              process.env.APERTURE_FIXTURE_POLICY || "V1",
          },
    },
    { command: "npm run dev", url: "http://127.0.0.1:5173" },
  ],
});
