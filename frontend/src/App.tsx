/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React, { useState, useEffect } from "react";
import { BrowserRouter as Router, Routes, Route, useParams, Navigate, Link} from "react-router";
import ProjectMgmt from "./ProjectMgmt";
import NewProject from "./NewProject";
import ActionsProjectsList from "./ActionsProjectsList";
import AddActionsProject from "./AddActionsProject";
import ActionsProjectDetail from "./ActionsProjectDetail";
import DarkModeToggle from "./components/DarkModeToggle";
import BrandLogo from "./components/BrandLogo";
import WorkspaceMembers from "./components/WorkspaceMembers";
import WorkspaceNotifications from "./components/WorkspaceNotifications";
import { ThemeProvider } from "./components/ThemeContext";
import { checkGitHubPermissions, getUserDetails, loginWithGitHubToken, logout, PermissionValidationResult, UserDetails } from "./api/user";
import config from "./config";
import PermissionAlert from "./components/PermissionAlert";
import ToastContainer from "./components/Toast";
import { getDocsUrl } from "./help/helpLinks";

// Constants for URLs
const BACKEND_URL = config.BACKEND_URL;
const WEBSOCKET_URL = config.WEBSOCKET_URL;

// TypeScript interfaces

interface ProjectMgmtWrapperProps {
  readonly userDetails: UserDetails | undefined;
  readonly onLogout: () => void;
}

function App(): React.ReactElement {
  const [user, setUser] = useState<string | null>(localStorage.getItem("github_user") || null);
  const [userDetails, setUserDetails] = useState<UserDetails | undefined>(undefined);
  const [logoutMessage, setLogoutMessage] = useState<string | null>(null);
  const [permissionStatus, setPermissionStatus] = useState<PermissionValidationResult | null>(null);
  const [permissionAlertDismissed, setPermissionAlertDismissed] = useState<boolean>(false);
  const [githubToken, setGitHubToken] = useState<string>("");
  const [githubTokenLoginError, setGitHubTokenLoginError] = useState<string | null>(null);
  const [isGitHubTokenLoginPending, setIsGitHubTokenLoginPending] = useState<boolean>(false);
  const [showHttpsWarning, setShowHttpsWarning] = useState<boolean>(false);

  // Check if connection is insecure (non-localhost HTTP). Confirm with the
  // backend whether ALLOW_INSECURE_HTTP was explicitly set before warning —
  // window.location alone can't know that, and would otherwise keep showing
  // this even after an admin deliberately opts in.
  useEffect(() => {
    const isLocalhost = globalThis.location.hostname === 'localhost'
      || globalThis.location.hostname === '127.0.0.1'
      || globalThis.location.hostname === '::1';
    const isHttp = globalThis.location.protocol === 'http:';

    if (!isHttp || isLocalhost) {
      setShowHttpsWarning(false);
      return;
    }

    fetch(`${BACKEND_URL}/`)
      .then((res) => res.json())
      .then((data) => setShowHttpsWarning(!data?.allow_insecure_http))
      .catch(() => setShowHttpsWarning(true));
  }, []);

  // Handle WebSocket Connection
  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryCount = 0;

    const handleSocketOpen = (): void => {
      console.info("WebSocket connected!");
      if (socket) {
        socket.send("Hello from frontend!");
      }
    };

    const handleSocketClose = (): void => {
      console.warn("WebSocket closed");
    };

    const retryConnection = (): void => {
      if (retryCount < 5) {
        retryCount++;
        const retryDelay = Math.min(3000 * 2 ** retryCount, 30000); // Exponential backoff
        setTimeout(connectWebSocket, retryDelay);
      }
    };

    const handleSocketError = (error: Event): void => {
      console.error("WebSocket error:", error);
      retryConnection();
    };

    const connectWebSocket = (): void => {
      if (!WEBSOCKET_URL) {
        console.warn("WebSocket URL not configured");
        return;
      }
      socket = new WebSocket(WEBSOCKET_URL);
      socket.onopen = handleSocketOpen;
      socket.onerror = handleSocketError;
      socket.onclose = handleSocketClose;
    };

    connectWebSocket();

    return () => {
      if (socket) socket.close();
    };
  }, []);

  // Handle Login
  const handleLogin = (): void => {
    globalThis.location.href = `${BACKEND_URL}/auth/github`;
  };

  const handleGitHubTokenLogin = async (): Promise<void> => {
    if (!githubToken.trim()) {
      setGitHubTokenLoginError("Enter a GitHub token to continue.");
      return;
    }

    try {
      setIsGitHubTokenLoginPending(true);
      setGitHubTokenLoginError(null);
      const result = await loginWithGitHubToken(githubToken);
      setUser(result.user);
      localStorage.setItem("github_user", result.user);
      setGitHubToken("");
    } catch (error: any) {
      setGitHubTokenLoginError(error?.message || "GitHub token login failed.");
    } finally {
      setIsGitHubTokenLoginPending(false);
    }
  };

  // Handle Logout
  const handleLogout = (): void => {
    void logout();
    // Clear frontend authentication state
    setUser(null);
    setUserDetails(undefined);
    localStorage.removeItem("github_user");
    
    // Set logout confirmation message
    setLogoutMessage("You've been logged out.");
    
    // Clear the message after 5 seconds
    setTimeout(() => {
      setLogoutMessage(null);
    }, 5000);

    // Navigate to home screen
    globalThis.history.replaceState({}, "", "/");
  };

  // Persist user in localStorage and fetch user details
  useEffect(() => {
    const urlParams = new URLSearchParams(globalThis.location.search);
    const username = urlParams.get("user");

    if (username) {
      setUser(username);
      localStorage.setItem("github_user", username);
    }
  }, []);

  // Fetch user details when user changes
  useEffect(() => {
    if (user) {
      let cancelled = false;

      getUserDetails(user).then((details: UserDetails | null) => {
        if (!cancelled && details) {
          setUserDetails(details);
        }
      });

      // Check GitHub permissions after user is set
      checkGitHubPermissions(user).then((status: PermissionValidationResult | null) => {
        if (cancelled) return;
        if (status) {
          setPermissionStatus(status);
          // Reset dismissed state when new permission check happens
          setPermissionAlertDismissed(false);

          // Log permission status for debugging
          if (!status.valid) {
            console.warn("⚠️ GitHub permission issues detected:", status);
          } else {
            console.log("✅ GitHub permissions validated successfully");
          }
        }
      });

      return () => {
        cancelled = true;
      };
    } else {
      setUserDetails(undefined);
      setPermissionStatus(null);
      setPermissionAlertDismissed(false);
    }
  }, [user]);

  return (
    <ThemeProvider>
      <Router>
        <ToastContainer />
        <div className="flex items-center justify-center min-h-screen w-full flex-col" style={{ padding: user ? "0" : "1.5rem" }}>
          {user ? (
            <>
              {/* Permission Alert - shown across all routes when there are permission issues or warnings */}
              {permissionStatus && (!permissionStatus.valid || (permissionStatus.warnings?.length ?? 0) > 0) && !permissionAlertDismissed && (
                <div className="w-full max-w-7xl px-4 pt-4">
                  <PermissionAlert
                    permissionStatus={permissionStatus}
                    onDismiss={() => setPermissionAlertDismissed(true)}
                    onReconnect={handleLogin}
                  />
                </div>
              )}
              <Routes>
                <Route
                  path="/project/:user/:projectName"
                  element={<ProjectMgmtWrapper userDetails={userDetails} onLogout={handleLogout} />}
                />
                <Route
                  path="/project/:user/new"
                  element={<NewProjectWrapper />}
                />
                <Route
                  path="/project/:user"
                  element={<ProjectMgmtWrapper userDetails={userDetails} onLogout={handleLogout} />}
                />
                <Route
                  path="/workspace/members"
                  element={<WorkspaceMembersWrapper currentUser={user || ""} currentUserRole={userDetails?.workspace_role} onLogout={handleLogout} />}
                />
                <Route
                  path="/workspace/notifications"
                  element={<WorkspaceNotificationsWrapper currentUser={user || ""} currentUserRole={userDetails?.workspace_role} onLogout={handleLogout} />}
                />
                <Route
                  path="/project/:user/actions-projects/new"
                  element={<AddActionsProjectWrapper />}
                />
                <Route
                  path="/project/:user/actions-projects/:actionsProjectId"
                  element={<ActionsProjectDetailWrapper />}
                />
                <Route
                  path="/project/:user/actions-projects"
                  element={<ActionsProjectsListWrapper />}
                />
                <Route path="*" element={<Navigate to={`/project/${user}`} replace />} />
              </Routes>
            </>
          ) : (
            <>
              <Routes>
                <Route path="*" element={
                  <>
                    <DarkModeToggle />
                    {logoutMessage && (
                      <div className="bg-success-light text-success border border-success rounded-lg px-6 py-3 mb-6 text-sm font-medium text-center max-w-sm w-full">
                        ✅ {logoutMessage}
                      </div>
                    )}
                    <div className="flex flex-col items-center justify-center bg-container dark:bg-container-dark p-12 rounded-2xl shadow-xl border border-border dark:border-border-dark max-w-sm w-full gap-8">
                      <BrandLogo variant="full" size="lg" />
                      <button
                        className="bg-primary text-white text-base font-medium py-3.5 px-8 border-0 rounded-lg cursor-pointer transition-all duration-200 shadow-md font-sans inline-flex items-center gap-2 hover:bg-primary-hover hover:shadow-lg hover:-translate-y-0.5 w-full justify-center"
                        onClick={handleLogin}
                      >
                        🔑 Log in with GitHub
                      </button>
                      <div className="w-full border-t border-border dark:border-border-dark pt-6 space-y-3">
                        {showHttpsWarning && (
                          <div className="rounded-lg border-2 border-red-500 bg-red-50 dark:bg-red-900/20 px-4 py-3 space-y-2">
                            <div className="flex items-start gap-2">
                              <span className="text-lg">⚠️</span>
                              <div className="flex-1">
                                <p className="text-sm font-semibold text-red-800 dark:text-red-200">
                                  Insecure Connection Warning
                                </p>
                                <p className="text-xs text-red-700 dark:text-red-300 mt-1">
                                  You are accessing this site over HTTP on a non-local address. PAT login may be blocked for security. 
                                  Use HTTPS in production or set <code className="bg-red-100 dark:bg-red-900/40 px-1 rounded">ALLOW_INSECURE_HTTP=true</code> to override.
                                </p>
                                <a
                                  className="text-xs font-medium text-red-600 dark:text-red-400 hover:underline mt-1 inline-block"
                                  href="https://actionsmanager.io/getting-started/https-setup.html"
                                  rel="noreferrer"
                                  target="_blank"
                                >
                                  HTTPS setup guide →
                                </a>
                              </div>
                            </div>
                          </div>
                        )}
                        <div className="text-center">
                          <p className="text-sm font-medium text-text-primary dark:text-text-primary-dark">
                            Sign in with a Personal Access Token
                          </p>
                          <p className="mt-1 text-xs text-text-secondary dark:text-secondary-dark">
                            Fine-grained personal access tokens are recommended. OAuth remains the default when you have an OAuth app configured.
                          </p>
                        </div>
                        <input
                          aria-label="Personal Access Token login"
                          autoComplete="off"
                          className="w-full rounded-lg border border-border dark:border-border-dark bg-white dark:bg-gray-800 px-3 py-2.5 text-sm text-text-primary dark:text-text-primary-dark"
                          onChange={(event) => setGitHubToken(event.target.value)}
                          placeholder="Paste fine-grained or classic PAT"
                          type="password"
                          value={githubToken}
                        />
                        <div className="flex items-center justify-between gap-3">
                          <a
                            className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
                            href="https://github.com/settings/tokens"
                            rel="noreferrer"
                            target="_blank"
                          >
                            GitHub developer settings
                          </a>
                          <button
                            className="bg-secondary text-white text-sm font-medium py-2 px-4 border-0 rounded-lg cursor-pointer transition-all duration-200 shadow-sm hover:bg-secondary-hover disabled:cursor-not-allowed disabled:opacity-60"
                            disabled={isGitHubTokenLoginPending}
                            onClick={() => { void handleGitHubTokenLogin(); }}
                          >
                            {isGitHubTokenLoginPending ? "Signing in…" : "Sign in with token"}
                          </button>
                        </div>
                        <p className="text-xs text-text-secondary dark:text-secondary-dark">
                          Minimum recommended permissions: Metadata read, Contents read/write, Actions read/write, and Pull requests / Secrets / Variables only when you need those features.
                        </p>
                        <a
                          className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
                          href={getDocsUrl("patSetup")}
                          rel="noreferrer"
                          target="_blank"
                        >
                          PAT setup guide →
                        </a>
                        {githubTokenLoginError && (
                          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-200">
                            {githubTokenLoginError}
                          </div>
                        )}
                      </div>
                    </div>
                  </>
                } />
              </Routes>
            </>
          )}
        </div>
      </Router>
    </ThemeProvider>
  );
}

// Wrapper to pass URL parameters to ProjectMgmt
function ProjectMgmtWrapper({ userDetails, onLogout }: ProjectMgmtWrapperProps): React.ReactElement {
  return <ProjectMgmt userDetails={userDetails} onLogout={onLogout} />;
}

// Wrapper to pass URL parameters to NewProject
function NewProjectWrapper(): React.ReactElement {
  const { user } = useParams<{ user: string }>();
  return <NewProject user={user || ""} />;
}

// Shared header for the standalone Actions Projects pages (list/add/detail).
function ActionsProjectsPageShell({
  user,
  children,
}: {
  readonly user: string;
  readonly children: React.ReactNode;
}): React.ReactElement {
  return (
    <div className="w-full min-h-screen bg-background dark:bg-background-dark">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border dark:border-border-dark">
        <BrandLogo variant="full" size="sm" />
        <Link
          to={`/project/${user}`}
          className="text-sm text-text-secondary dark:text-secondary-dark hover:text-text-primary dark:hover:text-text-primary-dark transition-colors"
        >
          ← Back to Projects
        </Link>
      </div>
      <div className="p-6">{children}</div>
    </div>
  );
}

function ActionsProjectsListWrapper(): React.ReactElement {
  const { user } = useParams<{ user: string }>();
  return (
    <ActionsProjectsPageShell user={user || ""}>
      <ActionsProjectsList user={user || ""} />
    </ActionsProjectsPageShell>
  );
}

function AddActionsProjectWrapper(): React.ReactElement {
  const { user } = useParams<{ user: string }>();
  return (
    <ActionsProjectsPageShell user={user || ""}>
      <AddActionsProject user={user || ""} />
    </ActionsProjectsPageShell>
  );
}

function ActionsProjectDetailWrapper(): React.ReactElement {
  const { user, actionsProjectId } = useParams<{ user: string; actionsProjectId: string }>();
  return (
    <ActionsProjectsPageShell user={user || ""}>
      <ActionsProjectDetail user={user || ""} actionsProjectId={Number(actionsProjectId)} />
    </ActionsProjectsPageShell>
  );
}

// Wrapper for workspace members page with header/navigation
interface WorkspaceMembersWrapperProps {
  readonly currentUser: string;
  readonly currentUserRole?: string;
  readonly onLogout: () => void;
}

function WorkspaceMembersWrapper({ currentUser, currentUserRole, onLogout }: WorkspaceMembersWrapperProps): React.ReactElement {
  return (
    <div className="w-full min-h-screen bg-background dark:bg-background-dark">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border dark:border-border-dark">
        <BrandLogo variant="full" size="sm" />
        <div className="flex items-center gap-4">
          <Link
            to={`/project/${currentUser}`}
            className="text-sm text-text-secondary dark:text-secondary-dark hover:text-text-primary dark:hover:text-text-primary-dark transition-colors"
          >
            ← Back to Projects
          </Link>
          <button
            className="text-sm text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 transition-colors"
            onClick={onLogout}
          >
            Log out
          </button>
        </div>
      </div>
      <div className="p-6">
        <WorkspaceMembers currentUser={currentUser} currentUserRole={currentUserRole} />
      </div>
    </div>
  );
}

// Wrapper for workspace notifications page with header/navigation
interface WorkspaceNotificationsWrapperProps {
  readonly currentUser: string;
  readonly currentUserRole?: string;
  readonly onLogout: () => void;
}

function WorkspaceNotificationsWrapper({ currentUser, currentUserRole, onLogout }: WorkspaceNotificationsWrapperProps): React.ReactElement {
  return (
    <div className="w-full min-h-screen bg-background dark:bg-background-dark">
      <div className="flex items-center justify-between px-6 py-4 border-b border-border dark:border-border-dark">
        <BrandLogo variant="full" size="sm" />
        <div className="flex items-center gap-4">
          <Link
            to={`/project/${currentUser}`}
            className="text-sm text-text-secondary dark:text-secondary-dark hover:text-text-primary dark:hover:text-text-primary-dark transition-colors"
          >
            ← Back to Projects
          </Link>
          <button
            className="text-sm text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 transition-colors"
            onClick={onLogout}
          >
            Log out
          </button>
        </div>
      </div>
      <div className="p-6">
        <WorkspaceNotifications currentUser={currentUser} currentUserRole={currentUserRole} />
      </div>
    </div>
  );
}

export default App;
