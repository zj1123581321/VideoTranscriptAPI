import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Web 端纯函数用例：无 DOM 依赖，免 jsdom
    include: ['src/web/tests/**/*.test.js'],
    environment: 'node',
  },
});
