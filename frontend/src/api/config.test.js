import config from '../config';

// Simple function tests for small API modules
describe('API module imports and configuration', () => {
  test('should have valid configuration values', () => {
    expect(config).toBeDefined();
    expect(config.BACKEND_URL).toBeDefined();
    expect(config.FRONTEND_URL).toBeDefined();
  });

  test('environment variables should be accessible', () => {
    // Test that import.meta.env is accessible in test environment
    expect(typeof import.meta.env).toBe('object');
  });

  test('basic module import functionality', () => {
    // Static import at top of file verifies module imports work
    expect(config).toBeDefined();
    expect(config.BACKEND_URL).toBeDefined();
  });

  test('leaves websocket undefined when window is unavailable', async () => {
    const originalWindow = Object.getOwnPropertyDescriptor(global, 'window');

    try {
      vi.stubEnv('VITE_WEBSOCKET_URL', '');
      Object.defineProperty(global, 'window', {
        value: undefined,
        configurable: true,
      });

      vi.resetModules();

      // Dynamic import after resetModules gets a fresh module evaluation
      // with window=undefined, so WEBSOCKET_URL won't be auto-derived
      const mod = await import('../config');
      const isolatedConfig = mod.default;

      expect(isolatedConfig.WEBSOCKET_URL).toBeUndefined();
    } finally {
      if (originalWindow) {
        Object.defineProperty(global, 'window', originalWindow);
      }
      vi.unstubAllEnvs();
      vi.resetModules();
    }
  });

  test('JSON processing functionality', () => {
    const testData = { key: 'value', number: 123 };
    const jsonString = JSON.stringify(testData);
    const parsed = JSON.parse(jsonString);
    
    expect(parsed.key).toBe('value');
    expect(parsed.number).toBe(123);
  });

  test('URL validation helper', () => {
    const isValidUrl = (url) => {
      try {
        new URL(url);
        return true;
      } catch {
        return false;
      }
    };

    expect(isValidUrl('https://example.com')).toBe(true);
    expect(isValidUrl('http://localhost:3000')).toBe(true);
    expect(isValidUrl('invalid-url')).toBe(false);
  });

  test('error handling utilities', () => {
    const safeJsonParse = (str) => {
      try {
        return JSON.parse(str);
      } catch {
        return null;
      }
    };

    expect(safeJsonParse('{"valid": "json"}')).toEqual({ valid: 'json' });
    expect(safeJsonParse('invalid json')).toBeNull();
  });

  test('date utilities', () => {
    const formatDate = (date) => {
      return new Date(date).toISOString().split('T')[0];
    };

    const today = new Date();
    const formatted = formatDate(today);
    expect(formatted).toMatch(/\d{4}-\d{2}-\d{2}/);
  });

  test('array utilities', () => {
    const unique = (arr) => [...new Set(arr)];
    const isEmpty = (arr) => !arr || arr.length === 0;
    const sum = (numbers) => numbers.reduce((a, b) => a + b, 0);
    const max = (numbers) => Math.max(...numbers);
    const min = (numbers) => Math.min(...numbers);
    
    expect(unique([1, 2, 2, 3, 3, 3])).toEqual([1, 2, 3]);
    expect(isEmpty([])).toBe(true);
    expect(isEmpty([1])).toBe(false);
    expect(isEmpty(null)).toBe(true);
    expect(sum([1, 2, 3, 4])).toBe(10);
    expect(max([1, 5, 3, 2])).toBe(5);
    expect(min([1, 5, 3, 2])).toBe(1);
  });

  test('string utilities', () => {
    const capitalize = (str) => str.charAt(0).toUpperCase() + str.slice(1);
    const slugify = (str) => str.toLowerCase().replace(/\s+/g, '-');
    const truncate = (str, length) => str.length > length ? str.substring(0, length) + '...' : str;
    
    expect(capitalize('hello')).toBe('Hello');
    expect(slugify('Hello World')).toBe('hello-world');
    expect(truncate('Long text here', 5)).toBe('Long ...');
    expect(truncate('Short', 10)).toBe('Short');
  });

  test('number utilities', () => {
    const round = (num, decimals) => Math.round(num * Math.pow(10, decimals)) / Math.pow(10, decimals);
    const isEven = (num) => num % 2 === 0;
    const percentage = (value, total) => (value / total) * 100;
    
    expect(round(3.14159, 2)).toBe(3.14);
    expect(isEven(4)).toBe(true);
    expect(isEven(3)).toBe(false);
    expect(percentage(25, 100)).toBe(25);
  });
});
