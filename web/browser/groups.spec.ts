import { expect, test } from "@playwright/test";

for (const width of [1366, 390]) {
  test(`populated Groups ${width}`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 900 });
    const response = await request.get("http://127.0.0.1:8000/api/v1/groups");
    expect(response.ok()).toBe(true);
    const data = await response.json();
    expect(data.groups.length).toBeGreaterThan(0);
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/#groups");
    await expect(
      page.getByRole("heading", { name: "Groups", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("SYNTHETIC FIXTURE", { exact: true }).first(),
    ).toBeVisible();
    await expect(page.getByLabel("Group level").locator("option")).toHaveCount(
      6,
    );
    await page.getByLabel("Group level").selectOption("THEME");
    const theme = data.groups.find(
      (g: { group_type: string }) => g.group_type === "THEME",
    );
    await page.getByText(`${theme.group_id} · THEME`, { exact: true }).click();
    const detail = page.locator("details").first();
    await expect(detail).toContainText(
      `Source ${theme.membership.source_as_of_date}`,
    );
    await expect(detail).toContainText("leadership rank");
    await expect(detail).toContainText(theme.members[0].source_symbol);
    await page.getByLabel("Find group").fill("no matching group");
    await expect(page.locator("details")).toHaveCount(0);
    expect(errors).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  });
}
