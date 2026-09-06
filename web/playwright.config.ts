import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./browser",
  workers: 1,
  use: { baseURL: "http://127.0.0.1:5173", reducedMotion: "reduce" },
  webServer: [
    {
      command:
        "cd .. && .venv/bin/python -m uvicorn api.main:create_app --factory --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/api/v1/health",
      env: { APERTURE_MODE: "FIXTURE", APERTURE_FIXTURE_SCENARIO: "GREEN" },
    },
    { command: "npm run dev", url: "http://127.0.0.1:5173" },
  ],
});
