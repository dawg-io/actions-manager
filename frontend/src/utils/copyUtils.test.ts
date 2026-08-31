import { copyToClipboard } from './copyUtils';

Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn(() => Promise.resolve()),
  },
});

Object.defineProperty(window, 'isSecureContext', {
  writable: true,
  value: true,
});

const writeText = () => vi.mocked(navigator.clipboard.writeText);

describe('copyUtils', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('copyToClipboard', () => {
    test('should call clipboard API with text', async () => {
      const text = 'test text';

      writeText().mockResolvedValueOnce();

      await copyToClipboard(text);

      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(text);
    });

    test('should call onSuccess callback when successful', async () => {
      const onSuccess = vi.fn();
      const text = 'test text';

      writeText().mockResolvedValueOnce();

      await copyToClipboard(text, onSuccess);

      expect(onSuccess).toHaveBeenCalled();
    });

    test('should handle errors gracefully', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const onError = vi.fn();
      const text = 'test text';

      writeText().mockRejectedValueOnce(new Error('Clipboard error'));

      await copyToClipboard(text, undefined, onError);

      expect(onError).toHaveBeenCalledWith(expect.any(Error));

      consoleSpy.mockRestore();
    });
  });
});
