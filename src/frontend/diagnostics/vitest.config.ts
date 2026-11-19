import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(viteConfig, defineConfig({
  test: {
    environment: 'jsdom',
    // the unit suite is tests/ and nothing else, so a browser spec added later is never collected here
    include: ['tests/**/*.test.ts'],
    // what jsdom lacks and the facet bar's menus need (Y1.a)
    setupFiles: ['./tests/setup.ts'],
  },
}))
