import { test, expect } from "@playwright/test";

const evidenceDir =
  process.env.APERTURE_SMOKE_EVIDENCE_DIR ?? "test-results/evidence";

for (const viewport of [
  { width: 1366, height: 900 },
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
      .getByRole("navigation")
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
      page.getByRole("columnheader", { name: "5 sessions", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("columnheader", { name: "21 sessions", exact: true }),
    ).toBeVisible();
    if (viewport.width === 390) {
      const scroll = page.locator(".table-scroll");
      expect(
        await scroll.evaluate((el) => el.scrollWidth > el.clientWidth),
      ).toBe(true);
      await page
        .getByRole("columnheader", { name: "Veto / status", exact: true })
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
    await expect(page.getByText("Decision checklist")).toBeVisible();
    await page.screenshot({
      path: `${evidenceDir}/detail-${viewport.width}.png`,
    });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).not.toBeVisible();
    await expect(
      page.getByRole("button", { name: "SIM110", exact: true }),
    ).toBeFocused();
    await page
      .getByRole("navigation")
      .getByRole("link", { name: /Rules/ })
      .click();
    await expect(
      page.getByRole("heading", { name: "Rules & evidence" }),
    ).toBeVisible();
    await page
      .getByRole("navigation")
      .getByRole("link", { name: /Tape/ })
      .click();
    await expect(
      page.getByRole("combobox", { name: "Decision", exact: true }),
    ).toHaveValue("ACT");
    await page
      .getByRole("navigation")
      .getByRole("link", { name: /Sizer/ })
      .click();
    await page.getByLabel("Exact symbol").fill("SIM110");
    await page.getByLabel("Proposed entry ($)").fill("104");
    await page.getByLabel("Proposed stop ($)").fill("100.8");
    await page.getByRole("button", { name: "Calculate size" }).click();
    await expect(
      page.getByRole("heading", { name: "Canonical sizing result" }),
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
