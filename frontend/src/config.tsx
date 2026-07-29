// config.ts
interface Config {
  FRONTEND_URL: string | undefined;
  BACKEND_URL: string | undefined;
  WEBSOCKET_URL: string | undefined;
  APP_VERSION: string | undefined;
}

// Derive the runtime origin from the browser's current location.
// This allows the pre-built self-hosted image to work correctly whether
// accessed via localhost, a server IP, or a custom domain — without
// requiring a rebuild.
//
// Configuration priority order:
//   1. VITE_BACKEND_URL / VITE_FRONTEND_URL / VITE_WEBSOCKET_URL (explicit)
//   2. VITE_APP_URL (maps from APP_URL via start.sh at container startup)
//   3. window.location auto-detection (default)
const _location =
  typeof globalThis.window !== "undefined" ? globalThis.location : undefined;
const _origin = _location?.origin;
const _wsProtocol = _location
  ? _location.protocol === "https:"
    ? "wss:"
    : "ws:"
  : undefined;
const _host = _location?.host;

// Simplified APP_URL for self-hosted deployments
const _appUrl = import.meta.env.VITE_APP_URL;

// Derive WebSocket URL from APP_URL if set, using URL parsing to avoid double-slashes
const _wsFromAppUrl = (() => {
  if (!_appUrl) return undefined;
  try {
    const u = new URL(_appUrl);
    const wsProtocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${wsProtocol}//${u.host}/ws`;
  } catch {
    return undefined;
  }
})();

const config: Config = {
  FRONTEND_URL: import.meta.env.VITE_FRONTEND_URL || _appUrl || _origin,
  BACKEND_URL: import.meta.env.VITE_BACKEND_URL || _appUrl || _origin,
  WEBSOCKET_URL:
    import.meta.env.VITE_WEBSOCKET_URL ||
    _wsFromAppUrl ||
    (_wsProtocol && _host ? `${_wsProtocol}//${_host}/ws` : undefined),
  APP_VERSION: import.meta.env.VITE_APP_VERSION,
};

export default config;
