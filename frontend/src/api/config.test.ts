import config from '../config';

describe('config', () => {
  test('exposes the URLs the app reads at startup', () => {
    expect(config.BACKEND_URL).toBeDefined();
    expect(config.FRONTEND_URL).toBeDefined();
  });

  test('leaves websocket undefined when window is unavailable', async () => {
    const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');

    try {
      vi.stubEnv('VITE_WEBSOCKET_URL', '');
      Object.defineProperty(globalThis, 'window', {
        value: undefined,
        configurable: true,
      });

      vi.resetModules();

      // Dynamic import after resetModules gets a fresh module evaluation
      // with window=undefined, so WEBSOCKET_URL won't be auto-derived
      const { default: isolatedConfig } = await import('../config');

      expect(isolatedConfig.WEBSOCKET_URL).toBeUndefined();
    } finally {
      if (originalWindow) {
        Object.defineProperty(globalThis, 'window', originalWindow);
      }
      vi.unstubAllEnvs();
      vi.resetModules();
    }
  });
});
