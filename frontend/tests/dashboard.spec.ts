import { expect, test, type Page } from '@playwright/test';

async function ready(page: Page) {
  await page.goto('/');
  await expect(page.getByText('Backend healthy')).toBeVisible();
  await expect(page.getByTestId('district-map')).toHaveAttribute('data-ready', 'true');
  await expect(page.getByTestId('district-map')).toHaveAttribute('data-basemap', 'openstreetmap');
  await expect(page.locator('.map-attribution a')).toHaveText('© OpenStreetMap contributors');
  await expect(page.getByRole('button', { name: 'Run re-optimization', exact: true })).toBeEnabled();
}
async function run(page: Page) {
  const response = page.waitForResponse(r => r.url().endsWith('/api/optimize') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run re-optimization', exact: true }).click();
  const data = await (await response).json();
  await expect(page.getByRole('heading', { name: 'Compare the outcome' })).toBeVisible();
  return data;
}

test('real comparison, route inspection, views, layers and export', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await ready(page);
  await expect(page.locator('.scope-strip')).toContainText('Route H3 coverage');
  const response = await run(page);
  expect(response.feasible).toBe(true);
  expect(response.selected_routes.length).toBe(response.localization.affected_vehicles);
  await expect(page.locator('.scope-strip')).toContainText(`${response.route_h3_coverage.cell_count.toLocaleString()} cells · r${response.route_h3_coverage.resolution}`);
  await expect(page.getByText('Completed with validation')).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(6);
  if (response.comparison.qaoa_objective == null) {
    await expect(page.locator('.objective-row').filter({ hasText: 'QAOA' })).toContainText('Not run');
    await expect(page.getByText('Classical fallback.', { exact: true })).toBeVisible();
  }
  await page.locator('.vehicle-row').filter({ hasText: 'Courier 104' }).click();
  await expect(page.getByRole('complementary', { name: 'Route and run insights' }).getByRole('heading', { name: 'Courier 104' })).toBeVisible();
  await expect(page.getByText('Legal route candidates')).toBeVisible();
  await page.getByRole('button', { name: 'Before', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Before', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'After', exact: true }).click();
  await expect(page.getByRole('button', { name: 'After', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
  await page.getByLabel('Route H3 cells', { exact: true }).uncheck();
  await expect(page.getByLabel('Route H3 cells', { exact: true })).not.toBeChecked();
  await page.getByLabel('Route H3 cells', { exact: true }).check();
  await page.getByLabel('Incident H3 cells', { exact: true }).uncheck();
  await expect(page.getByLabel('Incident H3 cells', { exact: true })).not.toBeChecked();
  await page.getByRole('button', { name: 'Layers', exact: true }).click();
  await page.getByRole('button', { name: 'Fit district' }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export run' }).click();
  expect((await download).suggestedFilename()).toBe(`qhexroute-${response.run_id}.json`);
  expect(errors).toEqual([]);
});

test('settings invalidate results and update preview without recreating the map', async ({ page }) => {
  await ready(page); await run(page);
  const originalCanvas = await page.locator('.map-canvas canvas').elementHandle();
  const preview = page.waitForResponse(r => r.url().endsWith('/api/incidents/preview') && r.request().postDataJSON().severity === 4);
  await page.getByRole('slider', { name: 'Closure severity' }).focus();
  await page.keyboard.press('ArrowRight');
  expect((await (await preview).json()).incident.severity).toBe(4);
  await expect(page.getByRole('heading', { name: 'Your experiment results will appear here' })).toBeVisible();
  expect(await originalCanvas?.evaluate(el => el.isConnected)).toBe(true);
  await page.getByText('Experiment parameters', { exact: true }).click();
  const scenario = page.waitForResponse(r => r.url().includes('/api/scenario?seed=73'));
  await page.getByRole('spinbutton', { name: 'Simulation seed' }).fill('73');
  expect((await (await scenario).json()).seed).toBe(73);
  await expect(page.getByRole('button', { name: 'Run re-optimization', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Reset experiment' }).click();
  await expect(page.getByRole('slider', { name: 'Closure severity' })).toHaveValue('3');
  await expect(page.getByRole('spinbutton', { name: 'Simulation seed' })).toHaveValue('42');
});

test('map inspection preserves the incident; explicit placement and dragging preview a new incident', async ({ page }) => {
  await ready(page);
  let previews = 0;
  page.on('request', r => { if (r.url().endsWith('/api/incidents/preview')) previews++; });
  await page.getByRole('button', { name: 'Inspect Courier 104', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Courier 104', exact: true })).toBeVisible();
  expect(previews).toBe(0);
  await page.getByRole('button', { name: 'Fit district' }).click();
  await page.getByRole('button', { name: 'Place incident', exact: true }).click();
  const preview = page.waitForResponse(r => r.url().endsWith('/api/incidents/preview'));
  await page.locator('.map-canvas canvas').click({ position: { x: 290, y: 260 } });
  await preview;
  await expect(page.getByRole('button', { name: 'Inspect', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('combobox', { name: 'Test scenario' })).toHaveValue('Custom incident');
  const marker = await page.locator('.incident-marker').boundingBox();
  expect(marker).not.toBeNull();
  const dragged = page.waitForResponse(r => r.url().endsWith('/api/incidents/preview'));
  await page.mouse.move(marker!.x + marker!.width / 2, marker!.y + marker!.height / 2);
  await page.mouse.down(); await page.mouse.move(marker!.x + 60, marker!.y + 25, { steps: 8 }); await page.mouse.up();
  await dragged;
});

test('quiet corner keeps the fleet unchanged and district closure reports partial routing', async ({ page }) => {
  await ready(page);
  await page.getByRole('combobox', { name: 'Test scenario' }).selectOption('Quiet corner');
  await expect(page.getByRole('button', { name: 'Run re-optimization', exact: true })).toBeEnabled();
  const quiet = await run(page);
  expect(quiet.status).toBe('no_change'); expect(quiet.selected_routes).toHaveLength(0); expect(quiet.unaffected_routes).toHaveLength(6);
  await expect(page.getByText('No routes affected', { exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: 'Test scenario' }).selectOption('District closure');
  await expect(page.getByRole('button', { name: 'Run re-optimization', exact: true })).toBeEnabled();
  const closed = await run(page);
  expect(closed.status).toBe('partial'); expect(closed.feasible).toBe(false); expect(closed.unroutable_vehicle_ids.length).toBeGreaterThan(0);
  await expect(page.getByText('Partial · action required')).toBeVisible();
  await expect(page.getByText('All affected vehicles routed')).toHaveCount(0);
});

test('mobile coordinates, controls, run and experiment information are usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByTestId('district-map')).toHaveAttribute('data-ready', 'true');
  await page.getByRole('button', { name: 'Open controls' }).click();
  await expect(page.getByRole('heading', { name: 'Set up an incident' })).toBeVisible();
  await page.getByText('Incident coordinates', { exact: true }).click();
  await page.getByRole('spinbutton', { name: 'Incident latitude' }).fill('12.9782');
  await page.getByRole('spinbutton', { name: 'Incident longitude' }).fill('77.6064');
  await page.getByRole('button', { name: 'Apply coordinates' }).click();
  await expect(page.getByRole('button', { name: 'Run re-optimization', exact: true })).toBeEnabled();
  await run(page);
  await expect(page.getByRole('button', { name: 'Open controls' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('button', { name: 'About this experiment', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
});

test('failed optimization recovers with a useful retry', async ({ page }) => {
  await ready(page);
  await page.route('**/api/optimize', r => r.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Test service unavailable' }) }));
  await page.getByRole('button', { name: 'Run re-optimization', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Test service unavailable');
  await page.unroute('**/api/optimize');
  await page.getByRole('button', { name: 'Retry connection', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Run re-optimization', exact: true })).toBeEnabled();
  const data = await run(page);
  expect(data.feasible).toBe(true);
});

test('responsive layout has no horizontal page overflow and run remains in view on laptops', async ({ page }) => {
  await ready(page);
  for (const [width, height] of [[1440, 900], [1280, 800], [1024, 800], [768, 1024], [390, 844], [320, 740]]) {
    await page.setViewportSize({ width, height });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    if (width >= 1280) await expect(page.getByRole('button', { name: 'Run re-optimization', exact: true })).toBeInViewport();
  }
});
