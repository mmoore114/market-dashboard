import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi } from "vitest";
import { App } from "./App";
import fixture from "./__fixtures__/synthetic.json";
import { Context, number, money } from "./ui";
import type { Meta } from "./api";

function setup(
  options: {
    health?: unknown;
    empty?: boolean;
    failure?: boolean;
    pending?: boolean;
    refusal?: boolean;
    route?: string;
  } = {},
) {
  window.location.hash = options.route || "brief";
  const requests: { path: string; body?: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      requests.push({
        path,
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      });
      if (options.pending) return new Promise(() => {});
      if (options.failure)
        return new Response(
          JSON.stringify({
            schema_version: "workstation-error-v1",
            code: "SNAPSHOT_INVALID",
            message: "Snapshot validation failed.",
            mode_label: "LOCAL SNAPSHOT",
          }),
          { status: 503 },
        );
      const url = new URL(path, "http://localhost");
      let body: unknown;
      if (url.pathname.endsWith("/health"))
        body = options.health || fixture.health;
      else if (url.pathname.endsWith("/brief")) body = fixture.brief;
      else if (url.pathname.endsWith("/tape")) {
        let rows = fixture.tape.rows;
        const action = url.searchParams.get("action");
        if (action) rows = rows.filter((r) => r.decision === action);
        body = {
          ...fixture.tape,
          rows: options.empty ? [] : rows,
          total: options.empty ? 0 : rows.length,
        };
      } else if (url.pathname.includes("/symbols/")) body = fixture.detail;
      else if (url.pathname.endsWith("/rules")) body = fixture.rules;
      else body = options.refusal ? fixture.refusal : fixture.size;
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
  return { user: userEvent.setup(), requests };
}

describe("workstation", () => {
  it("renders fixture identity, freshness, five sleeves and the funnel", async () => {
    setup();
    expect(
      await screen.findByRole("heading", { name: "Daily brief" }),
    ).toBeVisible();
    expect(screen.getAllByText("SYNTHETIC FIXTURE").length).toBeGreaterThan(0);
    expect(screen.getByText("FRESH")).toBeVisible();
    const regime = screen.getByRole("region", { name: "Market regime" });
    expect(regime.querySelectorAll(".sleeves > div")).toHaveLength(5);
    const funnel = screen.getByRole("region", { name: "Decision funnel" });
    expect(
      [...funnel.querySelectorAll("strong")].map((n) => n.textContent),
    ).toEqual(["3", "1", "4", "4"]);
    expect(
      screen.getByText("Unavailable — portfolio context not implemented"),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Book Planned" })).toBeDisabled();
  });
  it("navigates routes, persists filters, sorts, and opens all detail evidence", async () => {
    const { user, requests } = setup({ route: "tape" });
    await screen.findByRole("heading", { name: "Research tape" });
    await user.selectOptions(screen.getByLabelText("Decision"), "ACT");
    await waitFor(() =>
      expect(requests.some((r) => r.path.includes("action=ACT"))).toBe(true),
    );
    await user.click(
      await screen.findByRole("button", { name: "Sort by Price" }),
    );
    await waitFor(() =>
      expect(requests.some((r) => r.path.includes("sort=price"))).toBe(true),
    );
    await user.click(screen.getByRole("link", { name: /Rules/ }));
    await screen.findByRole("heading", { name: "Rules & evidence" });
    await user.click(screen.getByRole("link", { name: /Tape/ }));
    expect(await screen.findByLabelText("Decision")).toHaveValue("ACT");
    await user.click(await screen.findByRole("button", { name: "SIM110" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Decision checklist")).toBeVisible();
    expect(within(dialog).getByText(/All setup instances/)).toBeVisible();
    expect(within(dialog).getByText("Review chart in Deepvue")).toBeVisible();
    await user.click(
      within(dialog).getByRole("button", { name: /Open Sizer what-if/ }),
    );
    expect(await screen.findByLabelText("Exact symbol")).toHaveValue("SIM110");
    const stored = JSON.parse(sessionStorage.getItem("aperture-ui-v1")!);
    expect(Object.keys(stored).sort()).toEqual(["filters", "selected"]);
  });
  it("shows nulls and veto explanations without zero substitution", async () => {
    setup({ route: "tape" });
    await screen.findByRole("button", { name: "SIM010" });
    expect(screen.getAllByText(/Unknown/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/reasons ·/).length).toBeGreaterThan(0);
    expect(number(null)).toBe("Unknown");
    expect(money(null)).toBe("Unknown");
  });
  it.each([false, true])(
    "submits canonical sizing and renders refusal=%s",
    async (refusal) => {
      const { user, requests } = setup({ route: "sizer", refusal });
      await user.type(await screen.findByLabelText("Exact symbol"), "SIM110");
      await user.type(screen.getByLabelText("Proposed entry ($)"), "104");
      await user.type(
        screen.getByLabelText("Proposed stop ($)"),
        refusal ? "110" : "100.8",
      );
      await user.click(screen.getByRole("button", { name: "Calculate size" }));
      expect(
        await screen.findByRole("heading", { name: "Canonical sizing result" }),
      ).toBeVisible();
      expect(
        requests.find((r) => r.path.endsWith("/sizer"))?.body,
      ).toMatchObject({
        symbol: "SIM110",
        direction: "LONG",
        entry: 104,
        stop: refusal ? 110 : 100.8,
        account_equity: 25000,
      });
      expect(screen.getAllByText("Unused risk")).toHaveLength(2);
      if (refusal) expect(screen.getByText(/Size refused/)).toBeVisible();
      expect(sessionStorage.getItem("aperture-ui-v1")).not.toContain("25000");
    },
  );
  it("shows a designed empty Tape", async () => {
    setup({ route: "tape", empty: true });
    expect(await screen.findByText("No matching candidates")).toBeVisible();
  });
  it("shows loading", () => {
    setup({ pending: true });
    expect(screen.getByText("Loading workstation")).toBeVisible();
  });
  it("shows sanitized API failure and retry", async () => {
    setup({ failure: true });
    expect(
      await screen.findByText("Snapshot validation failed."),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  });
  it.each(["STALE", "UNKNOWN"])(
    "blocks %s local snapshots and retains navigation",
    async (freshness) => {
      const { user } = setup({
        health: {
          ...fixture.health,
          available: false,
          meta: {
            ...fixture.health.meta,
            mode: "LOCAL_SNAPSHOT",
            mode_label: "LOCAL SNAPSHOT",
            freshness,
          },
        },
      });
      expect(
        await screen.findByText(
          freshness === "STALE" ? "Snapshot is stale" : "Snapshot unavailable",
        ),
      ).toBeVisible();
      expect(screen.queryByText("Daily brief")).not.toBeInTheDocument();
      await user.click(screen.getByRole("link", { name: /Sizer/ }));
      expect(screen.queryByLabelText("Exact symbol")).not.toBeInTheDocument();
      expect(screen.getAllByText("LOCAL SNAPSHOT").length).toBeGreaterThan(0);
    },
  );
  it("supports keyboard navigation and semantic form labels", async () => {
    const { user } = setup();
    await screen.findByText("Daily brief");
    await user.tab();
    expect(screen.getByText("Skip to research")).toHaveFocus();
    screen.getByRole("link", { name: /Sizer/ }).focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByLabelText("Account equity ($)")).toBeVisible();
  });
});

it("displays separate market, evaluation and action clocks with population scope", () => {
  const meta = {
    ...fixture.health.meta,
    as_of_session: "2026-09-04",
    action_session: "2026-09-08",
    evaluation: {
      market_as_of_session: "2026-09-04",
      evaluation_timestamp: "2026-09-06T21:00:00-04:00",
      action_session: "2026-09-08",
      population_scope: "Initial covered population",
      input_bindings: [],
    },
  } as Meta;
  render(<Context meta={meta} />);
  expect(screen.getByText("2026-09-04")).toBeInTheDocument();
  expect(screen.getByText("2026-09-08")).toBeInTheDocument();
  expect(screen.getByText("2026-09-06T21:00:00-04:00")).toBeInTheDocument();
  expect(screen.getByText("Initial covered population")).toBeInTheDocument();
});

it("labels bootstrap counts, retrospective limits and New York evaluation time", () => {
  const meta = {
    ...fixture.health.meta,
    mode: "LOCAL_SNAPSHOT",
    mode_label: "LOCAL SNAPSHOT",
    as_of_session: "2026-09-04",
    action_session: "2026-09-08",
    evaluation: {
      market_as_of_session: "2026-09-04",
      evaluation_timestamp: "2026-09-07T01:53:42.451047+00:00",
      action_session: "2026-09-08",
      population_scope: "bounded initial covered population",
      source_fingerprint: "a".repeat(64),
      input_bindings: [],
      bootstrap: {
        version: "current-state-bootstrap-v1",
        calculation_mode: "CURRENT_STATE_BOOTSTRAP",
        historical_membership_status: "UNKNOWN_BEFORE_BOOTSTRAP",
        population_scope: "bounded initial covered population",
        rank_basis: "CURRENT_COHORT_AT_E",
        market_as_of_session: "2026-09-04",
        evaluation_timestamp: "2026-09-07T01:53:42.451047+00:00",
        action_session: "2026-09-08",
        calculation_start: "2024-01-02",
        first_observations: [["SYNTHETIC", "2024-01-02"]],
        covered_population: 1,
        strict_trade_members: 1,
        mapping_members: 0,
        not_yet_observed: 0,
        missing_observations: 0,
      },
    },
  } as Meta;
  render(<Context meta={meta} />);
  expect(screen.getByText("CURRENT_STATE_BOOTSTRAP")).toBeVisible();
  expect(screen.getByText("UNKNOWN_BEFORE_BOOTSTRAP")).toBeVisible();
  expect(screen.getByText(/Sep 6, 2026/)).toBeVisible();
  expect(
    screen.getByText(/Covered 1; research 1; strict trade 1; mapping 0/),
  ).toBeVisible();
  expect(screen.getByText("a".repeat(64))).toBeVisible();
});
