import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react-swc';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    allowedHosts: true,
    watch: {
      // Enable polling for Docker volume mounts
      usePolling: true,
      interval: 1000,
    },
  },
  build: {
    // Keep CRA's output directory so nginx/Dockerfiles need no changes
    outDir: 'build',
    sourcemap: false,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    css: true,
    exclude: ['e2e/**', 'docs-screenshots/**', '**/node_modules/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'clover', 'json'],
      reportsDirectory: './coverage',
      thresholds: { lines: 5, functions: 5, branches: 5, statements: 5 },
    },
  },
});
