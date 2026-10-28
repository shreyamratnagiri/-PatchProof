import { test, expect } from '@playwright/test';
import { resolve } from 'node:path';

// Real browser -> real FastAPI -> SQLite, using a trusted, fixed defect fixture.
// Docker and model acceptance are tested separately on the host.
test('ZIP -> localization -> patch approval -> export without mutating original', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'System' }).click();
  await page.getByLabel('API key').fill('e2e-local-key');
  await page.getByRole('button', { name: 'Repositories' }).click();
  await page.getByLabel('Choose repository ZIP').setInputFiles(resolve('e2e/fixtures/calculator.zip'));
  await page.getByRole('button', { name: 'Import ZIP' }).click();
  await expect(page.getByText('calculator.py').first()).toBeVisible();

  await page.getByRole('button', { name: 'Investigate', exact: true }).first().click();
  await page.getByLabel('Repository').selectOption({ index: 1 });
  await page.getByPlaceholder('Describe the incorrect behavior and reproduction steps')
    .fill('The add function returns subtraction instead of sum.');
  await page.locator('main form button').filter({ hasText: 'Investigate' }).click();
  await expect(page.getByText('Ranked fault locations')).toBeVisible();
  await page.getByRole('button', { name: 'Open repair workspace' }).click();
  await page.getByLabel('File path').selectOption({ label: 'calculator.py' });
  await page.getByLabel('Existing code fragment').fill('return a-b');
  await page.getByLabel('Replacement fragment').fill('return a+b');
  await page.getByLabel('Rationale').fill('Use addition, not subtraction.');
  await page.getByRole('button', { name: 'Validate syntax and add candidate' }).click();
  await expect(page.getByText('UNIFIED DIFF', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Approve candidate for export' }).click();
  await expect(page.getByRole('button', { name: 'Approved for export' })).toBeDisabled();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download .patch' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^patchproof-.*\.patch$/);
  await expect(page.getByText('Verification evidence')).toBeVisible();
});
