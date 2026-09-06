import js from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['src/api.generated.ts', 'dist', 'node_modules'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  { languageOptions: { globals: { window: 'readonly', document: 'readonly', navigator: 'readonly', fetch: 'readonly', sessionStorage: 'readonly', console: 'readonly', URLSearchParams: 'readonly', RequestInit: 'readonly', RequestInfo: 'readonly', Response: 'readonly', AbortSignal: 'readonly' } } },
);
