// Vitest does not expose a `jest` global; this shim maps it to `vi`
// so that legacy test files and manual mocks that use jest.mock / jest.fn()
// continue to work without modification.
import { vi } from 'vitest';
(globalThis as unknown as Record<string, unknown>).jest = vi;
