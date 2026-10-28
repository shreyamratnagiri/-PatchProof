import { defineConfig } from '@playwright/test';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// Browser tests must never migrate or store artifacts in the application DB.
// This runner owns the disposable directory and deletes only that directory.
const e2eRoot = mkdtempSync(join(tmpdir(), 'patchproof-browser-e2e-'));
process.on('exit', () => rmSync(e2eRoot, { recursive: true, force: true }));
const sqliteUrl = `sqlite:///${join(e2eRoot, 'browser.db').replace(/\\/g, '/')}`;

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  use: { baseURL: 'http://127.0.0.1:5173' },
  webServer: [
    {
      command: 'python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000',
      cwd: '../..',
      url: 'http://127.0.0.1:8000/ready',
      reuseExistingServer: false,
      env: {
        PATCHPROOF_API_KEY: 'e2e-local-key',
        PATCHPROOF_DATABASE_URL: sqliteUrl,
        PATCHPROOF_DATA: join(e2eRoot, 'repos'),
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
    },
  ],
});
