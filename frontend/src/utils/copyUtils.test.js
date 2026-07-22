import { copyToClipboard } from './copyUtils';

// Mock the clipboard API
Object.assign(navigator, {
  clipboard: {
    writeText: jest.fn(() => Promise.resolve()),
  },
});

// Mock window.isSecureContext for testing
Object.defineProperty(window, 'isSecureContext', {
  writable: true,
  value: true
});

describe('copyUtils', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('copyToClipboard', () => {
    test('should call clipboard API with text', async () => {
      const text = 'test text';
      
      navigator.clipboard.writeText.mockResolvedValueOnce();

      await copyToClipboard(text);

      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(text);
    });

    test('should call onSuccess callback when successful', async () => {
      const onSuccess = jest.fn();
      const text = 'test text';
      
      navigator.clipboard.writeText.mockResolvedValueOnce();

      await copyToClipboard(text, onSuccess);

      expect(onSuccess).toHaveBeenCalled();
    });

    test('should handle errors gracefully', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
      const onError = jest.fn();
      const text = 'test text';
      
      navigator.clipboard.writeText.mockRejectedValueOnce(new Error('Clipboard error'));

      await copyToClipboard(text, null, onError);

      expect(onError).toHaveBeenCalledWith(expect.any(Error));
      
      consoleSpy.mockRestore();
    });
  });
});