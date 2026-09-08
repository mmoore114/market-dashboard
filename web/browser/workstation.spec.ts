import { test, expect } from "@playwright/test";

const evidenceDir =
  process.env.APERTURE_SMOKE_EVIDENCE_DIR ?? "test-results/evidence";

for (const viewport of [
  { width: 1366, height: 768 },
  { width: 390, height: 844 },
]) {
  test(`fixture workstation at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Daily brief" }),
    ).toBeVisible();
    await expect(page.getByText("SYNTHETIC FIXTURE").first()).toBeVisible();
    await page.screenshot({
      path: `${evidenceDir}/brief-${viewport.width}.png`,
      fullPage: true,
    });
    await page
      .getByRole("navigation", { name: "Primary navigation" })
      .getByRole("link", { name: /Tape/ })
      .click();
    await page
      .getByRole("combobox", { name: "Decision", exact: true })
      .selectOption("ACT");
    await expect(
      page.getByRole("button", { name: "SIM110", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Sort by Price", exact: true })
      .click();
    await expect(
      page.getByRole("columnheader", { name: "Current setup", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("columnheader", { name: "Primary blocker", exact: true }),
    ).toBeVisible();
    if (viewport.width === 390) {
      const scroll = page
        .getByRole("table", { name: "Research tape", exact: true })
        .locator("..");
      expect(
        await scroll.evaluate((el) => el.scrollWidth > el.clientWidth),
      ).toBe(true);
      await page
        .getByRole("columnheader", { name: "Primary blocker", exact: true })
        .scrollIntoViewIfNeeded();
      expect(await scroll.evaluate((el) => el.scrollLeft > 0)).toBe(true);
      await page
        .getByRole("columnheader", { name: /Symbol/ })
        .scrollIntoViewIfNeeded();
    }
    await page.screenshot({
      path: `${evidenceDir}/tape-${viewport.width}.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: "SIM110", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Primary blockers" }),
    ).toBeVisible();
    await page.screenshot({
      path: `${evidenceDir}/detail-${viewport.width}.png`,
    });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).not.toBeVisible();
    await expect(
      page.getByRole("button", { name: "SIM110", exact: true }),
    ).toBeFocused();
    await page
      .getByRole("navigation", { name: "Primary navigation" })
      .getByRole("link", { name: /Rules/ })
      .click();
    await expect(
      page.getByRole("heading", { name: "Rules & evidence" }),
    ).toBeVisible();
    await page
      .getByRole("navigation", { name: "Primary navigation" })
      .getByRole("link", { name: /Tape/ })
      .click();
    await expect(
      page.getByRole("combobox", { name: "Decision", exact: true }),
    ).toHaveValue("ACT");
    await page
      .getByRole("navigation", { name: "Primary navigation" })
      .getByRole("link", { name: /Sizer/ })
      .click();
    await page.getByLabel("Symbol search").fill("SIM110");
    await page.getByLabel("Account equity ($)").fill("25000");
    await page.getByLabel("Available buying power ($)").fill("10000");
    await page.getByLabel("Proposed entry ($)").fill("104");
    await page.getByLabel("Proposed stop ($)").fill("100.8");
    await page.getByRole("button", { name: "Calculate size" }).click();
    await expect(
      page.getByRole("heading", { name: "Policy-qualified sizing" }),
    ).toBeVisible();
    await page.screenshot({
      path: `${evidenceDir}/sizer-${viewport.width}.png`,
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
  });
}

for (const width of [1366, 390]) {
  test(`alignment group handoff and dense comparison fixture ${width}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: width === 1366 ? 768 : 844 });
    await page.goto("/#groups");
    await page
      .getByRole("table", { name: "Ranked groups", exact: true })
      .locator("tbody button")
      .first()
      .click();
    await page.getByRole("button", { name: "Open members on Tape →" }).click();
    const tape = page.getByRole("table", {
      name: "Research tape",
      exact: true,
    });
    await expect(tape.locator("tbody tr").first()).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Clear group filter" }),
    ).toBeVisible();
    await tape.locator(".symbol-link").first().click();
    await expect(
      page.getByRole("dialog").getByText("Current setup:", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: /Size this idea/ }).click();
    await expect(page.getByLabel("Symbol search")).not.toHaveValue("");
    // Twelve industries are independently ranked by the synthetic backend.
    await page.goto("/#groups");
    await page.reload();
    const groups = page.getByRole("table", {
      name: "Ranked groups",
      exact: true,
    });
    await expect(groups.locator("tbody tr")).toHaveCount(12);
    const visibleRows = async (table: typeof groups) =>
      table.locator("tbody tr").evaluateAll(
        (rows) =>
          rows.filter((row) => {
            const box = row.getBoundingClientRect();
            return box.top >= 0 && box.bottom <= window.innerHeight;
          }).length,
      );
    if (width === 1366) {
      const count = await visibleRows(groups);
      console.log(`Alignment Groups visible rows: ${count}`);
      expect(count).toBeGreaterThanOrEqual(10);
    }
    await page.screenshot({ path: `${evidenceDir}/groups-${width}.png` });
    await page
      .getByRole("navigation", { name: "Primary navigation" })
      .getByRole("link", { name: "Tape", exact: true })
      .click();
    await page.getByRole("button", { name: "Reset filters" }).click();
    await expect(tape.locator("tbody tr").first()).toBeVisible();
    if (width === 1366) {
      const count = await visibleRows(tape);
      console.log(`Alignment Tape visible rows: ${count}`);
      expect(count).toBeGreaterThanOrEqual(10);
    }
    await page.screenshot({ path: `${evidenceDir}/tape-dense-${width}.png` });
    await tape.getByRole("button", { name: "SIM115", exact: true }).click();
    const blocker = page
      .getByRole("dialog")
      .getByText("Earnings not cleared", { exact: true });
    await expect(blocker).toBeVisible();
    const blockerBox = await blocker.boundingBox();
    expect(blockerBox!.y + blockerBox!.height).toBeLessThan(
      width === 1366 ? 768 : 844,
    );
    await page.screenshot({
      path: `${evidenceDir}/detail-blocked-${width}.png`,
    });
    await page.getByRole("button", { name: "Close symbol detail" }).click();
    await page.getByLabel("Tape direction").selectOption("SHORT");
    await expect(
      page.getByText("No stocks match these filters."),
    ).toBeVisible();
  });
}
