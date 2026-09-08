import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { Groups } from "./Groups";

it("shows independent capture ages, operator reuse warning and supersession", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            groups: [],
            reasons: [],
            membership_maintenance: [
              {
                role: "hierarchy",
                capture_date: "2026-09-07",
                age_days: 3,
                reuse_status: "REUSABLE",
                expires_at: "2026-09-21T00:00:00Z",
                warning_at: "2026-09-18T00:00:00Z",
                applies_to_snapshot_capture: true,
              },
              {
                role: "themes",
                capture_date: "2026-09-05",
                age_days: 5,
                reuse_status: "REFRESH_DUE",
                expires_at: "2026-09-12T00:00:00Z",
                warning_at: "2026-09-10T00:00:00Z",
                applies_to_snapshot_capture: false,
              },
            ],
          }),
        ),
    ),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <Groups />
    </QueryClientProvider>,
  );
  expect(
    await screen.findByText(/Hierarchy capture 2026-09-07/),
  ).toHaveTextContent("3 calendar days old");
  expect(screen.getByText(/Themes capture 2026-09-05/)).toHaveTextContent(
    "REFRESH_DUE",
  );
  expect(screen.getByText(/Themes capture 2026-09-05/)).toHaveTextContent(
    "reuse expires 2026-09-12",
  );
  expect(screen.getByText(/Themes capture 2026-09-05/)).toHaveTextContent(
    "Deepvue has not reconfirmed",
  );
  expect(screen.getByText(/Themes capture 2026-09-05/)).toHaveTextContent(
    "requires rebuilding",
  );
});
