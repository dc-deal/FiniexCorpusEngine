import pluginVue from 'eslint-plugin-vue'
import { withVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import stylistic from '@stylistic/eslint-plugin'

export default withVueTs(
  pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,
  {
    plugins: { '@stylistic': stylistic },
    rules: {
      // single quotes for every string literal; double quotes stay legal only where they spare an escaped apostrophe
      '@stylistic/quotes': ['error', 'single', { avoidEscape: true, allowTemplateLiterals: 'never' }],
    },
  },
  {
    // built, generated or left behind by a run: nobody here wrote it
    ignores: ['dist/**', 'node_modules/**', 'coverage/**', 'playwright-report/**', 'test-results/**',
      'src/types/api/diagnostics_api.ts'],
  },
)
