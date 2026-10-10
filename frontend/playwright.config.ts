import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 45_000,
  use: { baseURL: 'http://127.0.0.1:4321', trace: 'retain-on-failure' },
  webServer: [
    { command: 'npm run dev:backend', cwd: '..', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: true, timeout: 120_000 },
    { command: 'npm run dev:frontend', cwd: '..', url: 'http://127.0.0.1:4321', reuseExistingServer: true, timeout: 120_000 },
  ],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
