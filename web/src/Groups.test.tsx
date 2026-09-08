import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { Groups } from "./Groups";
import fixture from "./__fixtures__/synthetic.json";
it("shows unranked coverage and independent capture reuse without inventing ranks", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (path: string) =>
        new Response(
          JSON.stringify(
            path.includes("/health")
              ? {
                  ...fixture.research_health,
                  membership_maintenance: [
                    {
                      role: "hierarchy",
                      capture_date: "2026-09-07",
                      age_days: 3,
                      reuse_status: "REUSABLE",
                      expires_at: "2026-09-21T00:00:00Z",
                      applies_to_snapshot_capture: true,
                    },
                  ],
                }
              : {
                  ...fixture.research_groups,
                  rows: path.includes("include_unranked=true")
                    ? [
                        {
                          ...fixture.research_groups.rows[0],
                          leadership_rank: null,
                          reasons: ["INSUFFICIENT_COVERAGE"],
                        },
                      ]
                    : [],
                },
          ),
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
  const user = userEvent.setup();
  expect(await screen.findByText(/Hierarchy 3d old/)).toBeVisible();
  await user.click(screen.getByLabelText("Include unranked groups"));
  expect(await screen.findByText("Unranked")).toBeVisible();
  expect(screen.getByText("insufficient coverage")).toBeVisible();
  await user.click(screen.getByText("Membership & ranking details"));
  expect(screen.getByText(/operator-approved dated capture/)).toBeVisible();
});
