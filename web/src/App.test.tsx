import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";
import { App } from "./App";
import fixture from "./__fixtures__/synthetic.json";
import { money, number } from "./ui";
function setup(
  route = "brief",
  options: { stale?: boolean; failure?: boolean; short?: boolean } = {},
) {
  window.location.hash = route;
  sessionStorage.clear();
  window.scrollTo = vi.fn();
  const paths: string[] = [];
  const bodies: Record<string, unknown>[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      paths.push(path);
      const url = new URL(path, "http://localhost");
      let body: unknown;
      if (options.failure)
        return new Response(
          JSON.stringify({
            message: "Snapshot validation failed",
            code: "SNAPSHOT_INVALID",
          }),
          { status: 503 },
        );
      if (url.pathname.endsWith("/research/health"))
        body = fixture.research_health;
      else if (url.pathname.endsWith("/research/tape")) {
        const action = url.searchParams.get("action");
        const rows = fixture.research_tape.rows
          .map((r) =>
            options.short && r.symbol === "SIM110"
              ? { ...r, direction: "SHORT" }
              : r,
          )
          .filter((r) => !action || r.decision === action);
        body = { ...fixture.research_tape, rows, total: rows.length };
      } else if (url.pathname.endsWith("/research/groups"))
        body = fixture.research_groups;
      else if (url.pathname.endsWith("/research/members"))
        body = fixture.research_members;
      else if (url.pathname.endsWith("/research/symbols"))
        body = fixture.symbol_search;
      else if (url.pathname.endsWith("/health"))
        body = options.stale
          ? {
              ...fixture.health,
              available: false,
              meta: { ...fixture.health.meta, freshness: "STALE" },
            }
          : fixture.health;
      else if (url.pathname.endsWith("/brief")) body = fixture.brief;
      else if (url.pathname.includes("/symbols/")) {
        const detail = structuredClone(fixture.detail);
        if (options.short) {
          const short = structuredClone(detail.records[0]);
          short.output.decision.direction = "SHORT";
          detail.records.push(short);
        }
        body = detail;
      } else if (url.pathname.endsWith("/rules")) body = fixture.rules;
      else if (url.pathname.endsWith("/sizer")) {
        bodies.push(JSON.parse(String(init?.body)));
        body = fixture.size;
      }
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  const query = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={query}>
      <App />
    </QueryClientProvider>,
  );
  return { user: userEvent.setup(), paths, bodies };
}
describe("daily research workflow", () => {
  it("separates freshness from completeness and keeps technical identity secondary", async () => {
    setup();
    await screen.findByRole("heading", { name: "Daily brief" });
    expect(screen.getByText("FRESH")).toBeVisible();
    expect(screen.getByText(/Evidence:/)).toBeVisible();
    expect(
      screen
        .getByRole("region", { name: "Market regime" })
        .querySelectorAll(".sleeves>div"),
    ).toHaveLength(5);
    expect(screen.getByText(fixture.health.meta.fingerprint)).not.toBeVisible();
    expect(
      within(
        screen.getByRole("navigation", { name: "Primary navigation" }),
      ).queryByText("Time Machine"),
    ).toBeNull();
  });
  it("opens a Brief funnel count in filtered Tape", async () => {
    const { user, paths } = setup();
    await user.click(
      await screen.findByRole("button", { name: "Open WATCH candidates" }),
    );
    expect(await screen.findByLabelText("Decision")).toHaveValue("WATCH");
    await waitFor(() =>
      expect(
        paths.some(
          (p) => p.includes("/research/tape?") && p.includes("action=WATCH"),
        ),
      ).toBe(true),
    );
  });
  it("preserves Tape filter and sort when detail closes and sends symbol to Sizer", async () => {
    const { user, paths } = setup("tape");
    await user.selectOptions(await screen.findByLabelText("Decision"), "ACT");
    await user.click(screen.getByRole("button", { name: "Sort by Price" }));
    await user.click(await screen.findByRole("button", { name: "SIM110" }));
    let dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByRole("heading", { name: "Primary blockers" }),
    ).toBeVisible();
    await user.click(
      within(dialog).getByRole("button", { name: "Close symbol detail" }),
    );
    expect(screen.getByLabelText("Decision")).toHaveValue("ACT");
    expect(paths.some((p) => p.includes("sort=price"))).toBe(true);
    await user.click(screen.getByRole("button", { name: "SIM110" }));
    dialog = await screen.findByRole("dialog");
    await user.click(
      await within(dialog).findByRole("button", { name: /Size this idea/ }),
    );
    expect(await screen.findByLabelText("Symbol search")).toHaveValue("SIM110");
    expect(screen.getByLabelText("Direction")).toHaveValue("LONG");
  });
  it("hands the actual SHORT evidence direction to Sizer", async () => {
    const { user } = setup("tape", { short: true });
    await user.click(await screen.findByRole("button", { name: "SIM110" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(
      await within(dialog).findByRole("button", { name: /Size this idea/ }),
    );
    expect(await screen.findByLabelText("Symbol search")).toHaveValue("SIM110");
    expect(screen.getByLabelText("Direction")).toHaveValue("SHORT");
  });
  it("navigates ranked group to bounded member to detail and back", async () => {
    const { user, paths } = setup("groups");
    const group = fixture.research_groups.rows[0];
    await user.click(await screen.findByRole("button", { name: group.name }));
    expect(
      await screen.findByRole("table", { name: "Group members" }),
    ).toBeVisible();
    await waitFor(() =>
      expect(paths.some((p) => p.includes("/research/members?"))).toBe(true),
    );
    const member = fixture.research_members.members.find((m) => m.row)!;
    await user.click(
      await screen.findByRole("button", { name: member.symbol }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Close symbol detail" }),
    );
    expect(screen.getByRole("table", { name: "Group members" })).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: /Back to ranked groups/ }),
    );
    expect(screen.getByRole("table", { name: "Ranked groups" })).toBeVisible();
  });
  it("does not present blank proposals as invalid and submits explicit amounts", async () => {
    const { user, bodies } = setup("sizer");
    await user.type(await screen.findByLabelText("Symbol search"), "SIM110");
    expect(screen.queryByText("INVALID")).toBeNull();
    await user.type(screen.getByLabelText("Account equity ($)"), "25000");
    await user.type(
      screen.getByLabelText("Available buying power ($)"),
      "1000",
    );
    await user.type(screen.getByLabelText("Proposed entry ($)"), "104");
    await user.type(screen.getByLabelText("Proposed stop ($)"), "100.8");
    await user.click(screen.getByRole("button", { name: "Calculate size" }));
    await waitFor(() =>
      expect(bodies[0]).toMatchObject({
        symbol: "SIM110",
        direction: "LONG",
        account_equity: 25000,
        available_buying_power: 1000,
        entry: 104,
        stop: 100.8,
      }),
    );
  });
  it("shows readable rules with technical parameters collapsed", async () => {
    setup("rules");
    expect(
      await screen.findByRole("heading", { name: "Rules & evidence" }),
    ).toBeVisible();
    expect(screen.getAllByText(/\$1 billion/)[0]).toBeVisible();
    expect(screen.getAllByText(/\$50 million/)[0]).toBeVisible();
    expect(screen.getByText(fixture.rules.rules_fingerprint)).not.toBeVisible();
  });
  it("does not retry a capability with no historical data", async () => {
    const { paths } = setup("history");
    await screen.findByRole("heading", { name: "Time Machine" });
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(paths.some((p) => p.includes("time-machine"))).toBe(false);
  });
  it("blocks expired snapshots without rendering research", async () => {
    setup("brief", { stale: true });
    await screen.findByRole("heading", { name: "Snapshot is stale" });
    expect(screen.queryByRole("table")).toBeNull();
  });
  it("keeps unavailable numbers distinct from zero", () => {
    expect(number(null)).toBe("Unknown");
    expect(money(null)).toBe("Unknown");
  });
});
