import { expect, test } from "@playwright/test";

for (const width of [1366, 390]) {
  test(`engine comparison ${width}`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 900 });
    const health = await request.get("http://127.0.0.1:8000/api/v1/health");
    const payload = await health.json();
    expect(payload.meta.mode).toBe("LOCAL_SNAPSHOT");
    expect(payload.meta.evaluation.comparison.kind).toBe(
      "ENGINE_VERSION_COMPARISON",
    );
    expect(payload.meta.as_of_session).toBe("2026-09-04");
    expect(payload.meta.action_session).toBe("2026-09-08");
    expect(payload.meta.evaluation.evaluation_timestamp).toContain(
      "2026-09-07T01:53:42.451047",
    );
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/");
    await expect(
      page.getByText("ENGINE_VERSION_COMPARISON", { exact: true }),
    ).toBeVisible();
    if (!payload.available) {
      expect(payload.meta.freshness).toBe("STALE");
      for (const route of [
        "brief",
        "tape",
        "groups",
        "rules",
        "symbols/AAPL",
      ]) {
        const response = await request.get(
          `http://127.0.0.1:8000/api/v1/${route}`,
        );
        expect(response.status()).toBe(503);
        expect((await response.json()).code).toBe("SNAPSHOT_STALE");
      }
      expect(errors).toEqual([]);
      return;
    }
    await expect(page.getByText("Daily brief", { exact: true })).toBeVisible();
    const rules = await request.get("http://127.0.0.1:8000/api/v1/rules");
    const body = await rules.json();
    expect(body.versions.structure).toBe("structure-engine-v2");
    expect(body.versions.setup).toBe("setup-engine-v2");
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
    const detail = await request.get(
      `http://127.0.0.1:8000/api/v1/symbols/${first}`,
    );
    const inputs = (await detail.json()).records[0].output.inputs;
    expect(inputs.structure.engine_version).toBe("structure-engine-v2");
    expect(inputs.setups.engine_version).toBe("setup-engine-v2");
    await page.getByRole("button", { name: first, exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("link", { name: "Groups", exact: false }).click();
    await expect(
      page.getByText("GROUP_MEMBERSHIP_UNKNOWN", { exact: true }),
    ).toBeVisible();
    await page.getByRole("link", { name: "Sizer", exact: false }).click();
    await expect(page.getByRole("heading", { name: /Sizer/i })).toBeVisible();
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
    await page.getByRole("link", { name: "Rules", exact: false }).click();
    await expect(
      page.getByRole("heading", { name: "Structure V2", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Setup V2", exact: true }),
    ).toBeVisible();
    expect(errors).toEqual([]);
  });
}
