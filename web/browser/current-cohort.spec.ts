import { expect, test } from "@playwright/test";

for (const width of [1366, 390]) {
  test(`real current-cohort Workstation ${width}`, async ({
    page,
    request,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const health = await (
      await request.get("http://127.0.0.1:8000/api/v1/health")
    ).json();
    expect(health.meta.mode).toBe("LOCAL_SNAPSHOT");
    expect(health.available).toBe(true);
    expect(health.meta.freshness).toBe("FRESH");
    const groups = await (
      await request.get("http://127.0.0.1:8000/api/v1/groups")
    ).json();
    expect(groups.groups.length).toBeGreaterThan(300);
    expect(
      new Set(groups.groups.map((g: { group_type: string }) => g.group_type)),
    ).toEqual(
      new Set(["SECTOR", "GROUP", "INDUSTRY", "SUB_INDUSTRY", "THEME"]),
    );
    for (const g of groups.groups) {
      expect(g.membership.analysis_basis).toBe("CURRENT_COHORT_AT_E");
      expect(g.membership.market_as_of_session).toBe(health.meta.as_of_session);
      expect(g.membership.evaluation_timestamp).toBe(
        health.meta.evaluation.evaluation_timestamp,
      );
      expect(g.membership.action_session).toBe(health.meta.action_session);
      expect(g.rank_change_5).toBeNull();
      expect(g.rank_change_20).toBeNull();
    }
    if (process.env.APERTURE_MEMBERSHIP_POLICY) {
      expect(groups.membership_maintenance).toHaveLength(2);
      expect(
        groups.membership_maintenance.map((s: { role: string }) => s.role),
      ).toEqual(["hierarchy", "themes"]);
      expect(
        groups.membership_maintenance.every((s: { reuse_status: string }) =>
          ["REUSABLE", "REFRESH_DUE"].includes(s.reuse_status),
        ),
      ).toBe(true);
    }
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/#groups");
    await expect(
      page.getByRole("heading", { name: "Groups", exact: true }),
    ).toBeVisible();
    if (process.env.APERTURE_MEMBERSHIP_POLICY) {
      await expect(page.getByText(/Hierarchy capture/)).toContainText(
        "calendar days old",
      );
      await expect(page.getByText(/Themes capture/)).toContainText(
        "Deepvue has not reconfirmed",
      );
    }
    await page.getByLabel("Group level").selectOption("SECTOR");
    await page.locator("details").first().locator("summary").click();
    await expect(page.locator("details").first()).toContainText(
      "CURRENT COHORT",
    );
    await expect(
      page.locator("details").first().locator("li").first(),
    ).toBeVisible();
    await expect(page.locator("details").first()).toContainText(
      "Historical rotation changes unavailable",
    );
    for (const route of ["brief", "tape", "sizer", "rules"]) {
      await page
        .getByRole("navigation")
        .getByRole("link", { name: route, exact: false })
        .click();
      await expect(page.locator("main h1")).toBeVisible();
    }
    const rules = await (
      await request.get("http://127.0.0.1:8000/api/v1/rules")
    ).json();
    expect(rules.versions.structure).toBe("structure-engine-v2");
    expect(rules.versions.setup).toBe("setup-engine-v2");
    const detail = await request.get(
      "http://127.0.0.1:8000/api/v2/symbols/AAPL",
    );
    expect(detail.ok()).toBe(true);
    expect(errors).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  });
}
