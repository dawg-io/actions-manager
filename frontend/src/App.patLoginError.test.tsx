/**
 * The PAT login guard rejects any non-local HTTP request, which an HTTPS
 * deployment still trips when its reverse proxy does not forward the scheme.
 * The message alone leaves the admin to go looking, so the error carries the
 * HTTPS setup guide.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { loginWithGitHubToken } from "./api/user";
import { getDocsUrl } from "./help/helpLinks";

class StubWebSocket {
  close = vi.fn();
  send = vi.fn();
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
}
vi.stubGlobal("WebSocket", StubWebSocket);

vi.mock("./api/setup", () => ({
  isUninitialized: vi.fn().mockResolvedValue(false),
}));

vi.mock("./api/user", () => ({
  loginWithGitHubToken: vi.fn(),
  getUserDetails: vi.fn().mockResolvedValue(undefined),
  checkGitHubPermissions: vi.fn().mockResolvedValue(null),
  logout: vi.fn().mockResolvedValue(undefined),
  updateOnboardingState: vi.fn().mockResolvedValue(undefined),
}));

// Verbatim from backend/auth.py. The phrase the link keys off ("non-local
// HTTP") and the trailing guide URL are both asserted there by
// backend/tests/test_auth_http_security.py, so a reworded backend message
// fails that suite rather than silently dropping the link here.
const INSECURE_HTTP_DETAIL =
  "PAT login over non-local HTTP is disabled for security. " +
  "Use HTTPS or set ALLOW_INSECURE_HTTP=true to override. " +
  "Already behind an HTTPS reverse proxy? It must forward X-Forwarded-Proto: https. " +
  "Setup guide: https://actionsmanager.io/getting-started/https-setup.html";

async function submitToken() {
  const user = userEvent.setup();
  render(<App />);
  await user.type(await screen.findByLabelText("Personal Access Token login"), "ghp_test");
  await user.click(screen.getByRole("button", { name: "Sign in with token" }));
}

describe("PAT login error", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(loginWithGitHubToken).mockReset();
  });

  it("links the HTTPS setup guide when the connection guard rejects the login", async () => {
    vi.mocked(loginWithGitHubToken).mockRejectedValue(new Error(INSECURE_HTTP_DETAIL));

    await submitToken();

    await screen.findByText(/PAT login over non-local HTTP is disabled/);
    const guide = screen.getByRole("link", { name: /HTTPS setup guide/ });
    expect(guide).toHaveAttribute("href", getDocsUrl("httpsSetup"));
    expect(screen.queryByText(/Setup guide: https/)).toBeNull();
  });

  it("does not link the guide for an unrelated login failure", async () => {
    vi.mocked(loginWithGitHubToken).mockRejectedValue(new Error("Bad credentials"));

    await submitToken();

    await screen.findByText("Bad credentials");
    expect(screen.queryByRole("link", { name: /HTTPS setup guide/ })).toBeNull();
  });
});
