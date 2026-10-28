import {test,expect} from '@playwright/test';
test('navigation and API-key input',async({page})=>{await page.goto('/');await expect(page.getByText('Evidence-first software repair.')).toBeVisible();await page.getByRole('button',{name:'System'}).click();await page.getByLabel('API key').fill('development-test');await expect(page.getByLabel('API key')).toHaveValue('development-test');});
