import { expect, test } from "@playwright/test";

for (const width of [1366, 390]) {
  test(`real bootstrap ${width}`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 900 });
    const health = await request.get("http://127.0.0.1:8000/api/v1/health");
    const payload = await health.json();
    expect(payload.available).toBe(true);
    expect(payload.meta.mode).toBe("LOCAL_SNAPSHOT");
    expect(payload.meta.evaluation.bootstrap.calculation_mode).toBe(
      "CURRENT_STATE_BOOTSTRAP",
    );
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/");
    await expect(
      page.getByText("CURRENT_STATE_BOOTSTRAP", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Sep 6, 2026", { exact: false })).toBeVisible();
    await expect(
      page.getByText("Covered 101; research 75; strict trade 49; mapping 25"),
    ).toBeVisible();
    if (process.env.APERTURE_SMOKE_EVIDENCE_DIR)
      await page.screenshot({
        path: `${process.env.APERTURE_SMOKE_EVIDENCE_DIR}/brief-${width}.png`,
        fullPage: true,
      });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width + 2);
    await page
      .getByRole("navigation")
      .getByRole("link", { name: /Tape/ })
      .click();
    await expect(page.getByRole("table")).toBeVisible();
    const tape = await request.get(
      "http://127.0.0.1:8000/api/v1/tape?page_size=100",
    );
    const tapeBody = await tape.json();
    expect(tapeBody.total).toBe(75);
    const first = tapeBody.rows[0].symbol;
    for (const route of ["brief", "groups", "rules", `symbols/${first}`]) {
      expect(
        (await request.get(`http://127.0.0.1:8000/api/v1/${route}`)).status(),
      ).toBe(200);
    }
    expect(
      (
        await request.get("http://127.0.0.1:8000/api/v1/groups/UNAVAILABLE")
      ).status(),
    ).toBe(404);
    const sized = await request.post("http://127.0.0.1:8000/api/v1/sizer", {
      data: {
        symbol: first,
        direction: "LONG",
        account_equity: null,
        available_buying_power: null,
        entry: null,
        stop: null,
      },
    });
    expect(sized.status()).toBe(200);
    expect((await sized.json()).meta.fingerprint).toBe(
      payload.meta.fingerprint,
    );
    await page.getByRole("button", { name: first, exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("link", { name: "Groups", exact: false }).click();
    await expect(
      page.getByText("GROUP_MEMBERSHIP_UNKNOWN", { exact: true }),
    ).toBeVisible();
    await page.getByRole("link", { name: "Sizer", exact: false }).click();
    await expect(page.getByRole("heading", { name: /Sizer/i })).toBeVisible();
    await page.getByRole("link", { name: "Rules", exact: false }).click();
    await expect(
      page.getByRole("heading", { name: /Rules/i }).first(),
    ).toBeVisible();
    await page
      .getByRole("link", { name: "Time Machine", exact: false })
      .click();
    await expect(
      page.getByText("UNKNOWN_BEFORE_BOOTSTRAP", { exact: true }).last(),
    ).toBeVisible();
    const refused = await request.get(
      "http://127.0.0.1:8000/api/v1/time-machine/2026-09-04",
    );
    expect(refused.status()).toBe(422);
    expect((await refused.json()).code).toBe("UNKNOWN_BEFORE_BOOTSTRAP");
    expect(errors).toEqual([]);
  });
}
