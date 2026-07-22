/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_URL: string | undefined;
  readonly VITE_FRONTEND_URL: string | undefined;
  readonly VITE_WEBSOCKET_URL: string | undefined;
  readonly VITE_APP_URL: string | undefined;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
