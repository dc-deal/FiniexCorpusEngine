import { fileURLToPath } from 'node:url'
import { join } from 'node:path'
import { defineConfig, devices } from '@playwright/test'

// The browser check runs against the built UI as a reviewer gets it: the API process serves dist/. It starts its own
// process on its own port, so a server already running on 8001 for a person is left alone, and with --public-only, so no
// screenshot it leaves can hold a licensed title or page, whatever the machine holds; and with --no-chat, so no check can
// reach a model: the chat's answers come from fixtures in the browser.
const PORT = 8011
const ROOT = fileURLToPath(new URL('../../..', import.meta.url))
const PYTHON = join(ROOT, process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : '.venv/bin/python')

export default defineConfig({
  testDir: 'e2e',
  outputDir: 'test-results',
  // one browser, one server: the views read the same tracked data, and the run stays light on a laptop
  workers: 1,
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1400, height: 900 },
  },
  webServer: {
    command: `"${PYTHON}" -m backend.diagnostics --port ${PORT} --public-only --no-chat`,
    cwd: ROOT,
    url: `http://127.0.0.1:${PORT}/api/works`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
