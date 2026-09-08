import { test, expect } from "@playwright/test";
for (const width of [1366, 390])
  test(`daily research workflow ${width}`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: width === 1366 ? 768 : 844 });
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const health = await (await request.get("/api/v1/health")).json();
    expect(health.available).toBe(true);
    expect(health.meta.freshness).toBe("FRESH");
    const capture = async (name: string) => {
      await page.waitForLoadState("networkidle");
      if (process.env.APERTURE_UX_CAPTURES)
        await page.screenshot({
          path: `${process.env.APERTURE_UX_CAPTURES}/${name}-${width}.png`,
        });
    };
    const visibleRows = async (name: string) =>
      page
        .getByRole("table", { name, exact: true })
        .locator("tbody tr")
        .evaluateAll(
          (rows) =>
            rows.filter((r) => {
              const b = r.getBoundingClientRect();
              return b.top >= 0 && b.bottom <= window.innerHeight;
            }).length,
        );
    await page.goto("/#brief");
    await expect(
      page.getByRole("heading", { name: "Daily brief" }),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Market regime" }),
    ).toBeVisible();
    await capture("brief");
    await page.getByRole("button", { name: "Open WATCH candidates" }).click();
    await expect(
      page.getByRole("combobox", { name: "Decision", exact: true }),
    ).toHaveValue("WATCH");
    const tape = page.getByRole("table", {
      name: "Research tape",
      exact: true,
    });
    await expect(tape.locator("tbody tr").first()).toBeVisible();
    if (width === 1366) {
      const count = await visibleRows("Research tape");
      console.log(`Laptop Tape complete rows: ${count}`);
      expect(count).toBeGreaterThanOrEqual(10);
    }
    await capture("tape");
    const first = tape.locator(".symbol-link").first();
    const symbol = await first.innerText();
    await first.click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("heading", { name: "Primary blockers" }),
    ).toBeVisible();
    await expect(dialog.getByText(/Current setup:/)).toBeVisible();
    if (width === 1366) {
      const b = await dialog
        .getByRole("heading", { name: "Primary blockers" })
        .boundingBox();
      expect(b!.y + b!.height).toBeLessThan(768);
    }
    await capture("detail");
    await dialog.getByRole("tab", { name: "Setups", exact: true }).click();
    await expect(
      dialog.getByRole("heading", { name: /Active setups/ }),
    ).toBeVisible();
    await expect(dialog.getByText(/Terminal history/)).toBeVisible();
    await capture("setups");
    await dialog
      .getByRole("tab", { name: "Decision evidence", exact: true })
      .click();
    await expect(
      dialog.getByText("Complete original decision checklist"),
    ).toBeVisible();
    await expect(dialog.getByText("Missing evidence").first()).toBeVisible();
    await dialog.getByRole("button", { name: "Close symbol detail" }).click();
    await expect(
      page.getByRole("combobox", { name: "Decision", exact: true }),
    ).toHaveValue("WATCH");
    await first.click();
    await dialog.getByRole("button", { name: /Size this idea/ }).click();
    await expect(page.getByLabel("Symbol search")).toHaveValue(symbol);
    await expect(
      page.getByRole("combobox", { name: "Direction", exact: true }),
    ).toHaveValue("LONG");
    await capture("sizer");
    const nav = page.getByRole("navigation", { name: "Primary navigation" });
    await nav.getByRole("link", { name: "Groups", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Industries", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    const groups = page.getByRole("table", {
      name: "Ranked groups",
      exact: true,
    });
    await expect(groups.locator("tbody tr").first()).toBeVisible();
    await capture("groups");
    if (width === 1366) {
      const count = await visibleRows("Ranked groups");
      console.log(`Laptop Groups complete rows: ${count}`);
      expect(count).toBeGreaterThanOrEqual(10);
    }
    await groups.locator("tbody tr").first().getByRole("button").click();
    const members = page.getByRole("table", {
      name: "Group members",
      exact: true,
    });
    const member = members.locator(".symbol-link").first();
    await expect(member).toBeVisible();
    const memberSymbol = await member.innerText();
    await capture("members");
    await member.click();
    await expect(dialog.locator("#detail-title")).toContainText(memberSymbol);
    await dialog.getByRole("button", { name: "Close symbol detail" }).click();
    await expect(members).toBeVisible();
    await page.getByRole("button", { name: /Back to ranked groups/ }).click();
    await page.getByLabel("Include unranked groups").check();
    const unranked = await (
      await request.get(
        "/api/v2/research/groups?kind=INDUSTRY&include_unranked=true&page_size=100&page=1",
      )
    ).json();
    expect(
      unranked.rows.some(
        (g: { leadership_rank: number | null; reasons: string[] }) =>
          g.leadership_rank == null && g.reasons.length > 0,
      ),
    ).toBe(true);
    await nav.getByRole("link", { name: "Rules", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Rules & evidence" }),
    ).toBeVisible();
    await expect(
      page.locator(".rule-section > ul").getByText(/\$1 billion/),
    ).toBeVisible();
    await capture("rules");
    expect(errors).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  });
