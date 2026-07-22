import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import PermissionAlert from "./PermissionAlert";
import { PermissionValidationResult } from "../api/user";

describe("PermissionAlert", () => {
  const mockOnDismiss = jest.fn();
  const mockOnReconnect = jest.fn();

  beforeEach(() => {
    mockOnDismiss.mockClear();
    mockOnReconnect.mockClear();
  });

  it("should not render when permissions are valid and no warnings", () => {
    const validStatus: PermissionValidationResult = {
      status: "valid",
      valid: true,
      missing_scopes: [],
      granted_scopes: ["repo", "workflow", "read:org", "user:email"],
      issues: [],
      warnings: [],
      recommendations: [],
      message: "All permissions are valid",
    };

    const { container } = render(
      <PermissionAlert
        permissionStatus={validStatus}
        onDismiss={mockOnDismiss}
        onReconnect={mockOnReconnect}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it("should render alert when permissions are valid but warnings are present", () => {
    const validStatusWithWarnings: PermissionValidationResult = {
      status: "valid",
      valid: true,
      missing_scopes: [],
      granted_scopes: ["repo", "workflow", "read:org", "user:email"],
      issues: [],
      warnings: ["Repository access is limited by organization policy"],
      recommendations: ["Contact your organization administrator if access is still blocked."],
      message: "Permissions are valid, but some access may be restricted",
    };

    render(
      <PermissionAlert
        permissionStatus={validStatusWithWarnings}
        onDismiss={mockOnDismiss}
        onReconnect={mockOnReconnect}
      />
    );

    expect(screen.getByText("Warnings:")).toBeInTheDocument();
    expect(screen.getByText("Repository access is limited by organization policy")).toBeInTheDocument();
  });

  it("should render alert when permissions are invalid", () => {
    const invalidStatus: PermissionValidationResult = {
      status: "missing_scopes",
      valid: false,
      missing_scopes: ["repo", "workflow"],
      granted_scopes: ["user:email"],
      issues: ["Missing critical GitHub permissions: repo, workflow"],
      warnings: [],
      recommendations: [
        "Sign out and sign in again. When GitHub asks for permissions, make sure to authorize all requested scopes.",
      ],
      message: "Missing GitHub permissions",
    };

    render(
      <PermissionAlert
        permissionStatus={invalidStatus}
        onDismiss={mockOnDismiss}
        onReconnect={mockOnReconnect}
      />
    );

    expect(screen.getByText("Missing GitHub Permissions")).toBeInTheDocument();
    expect(screen.getByText(/Missing critical GitHub permissions/)).toBeInTheDocument();
  });

  it("should display missing scopes", () => {
    const status: PermissionValidationResult = {
      status: "missing_scopes",
      valid: false,
      missing_scopes: ["repo", "workflow"],
      granted_scopes: [],
      issues: ["Missing permissions"],
      warnings: [],
      recommendations: [],
      message: "",
    };

    render(<PermissionAlert permissionStatus={status} />);

    expect(screen.getByText("repo")).toBeInTheDocument();
    expect(screen.getByText("workflow")).toBeInTheDocument();
  });

  it("should display issues", () => {
    const status: PermissionValidationResult = {
      status: "missing_scopes",
      valid: false,
      missing_scopes: [],
      granted_scopes: [],
      issues: ["Issue 1", "Issue 2"],
      warnings: [],
      recommendations: [],
      message: "",
    };

    render(<PermissionAlert permissionStatus={status} />);

    expect(screen.getByText("Issues:")).toBeInTheDocument();
    expect(screen.getByText("Issue 1")).toBeInTheDocument();
    expect(screen.getByText("Issue 2")).toBeInTheDocument();
  });

  it("should display warnings", () => {
    const status: PermissionValidationResult = {
      status: "missing_org_approval",
      valid: false,
      missing_scopes: [],
      granted_scopes: [],
      issues: [],
      warnings: ["Organization restrictions detected"],
      recommendations: [],
      message: "",
    };

    render(<PermissionAlert permissionStatus={status} />);

    expect(screen.getByText("Warnings:")).toBeInTheDocument();
    expect(screen.getByText("Organization restrictions detected")).toBeInTheDocument();
  });

  it("should display recommendations", () => {
    const status: PermissionValidationResult = {
      status: "token_invalid",
      valid: false,
      missing_scopes: [],
      granted_scopes: [],
      issues: [],
      warnings: [],
      recommendations: [
        "Please sign out and sign in again",
        "Contact support if issue persists",
      ],
      message: "",
    };

    render(<PermissionAlert permissionStatus={status} />);

    expect(screen.getByText("How to Fix:")).toBeInTheDocument();
    expect(screen.getByText(/Please sign out and sign in again/)).toBeInTheDocument();
    expect(screen.getByText(/Contact support if issue persists/)).toBeInTheDocument();
  });

  it("should call onDismiss when dismiss button is clicked", () => {
    const status: PermissionValidationResult = {
      status: "missing_scopes",
      valid: false,
      missing_scopes: ["repo"],
      granted_scopes: [],
      issues: ["Missing permissions"],
      warnings: [],
      recommendations: [],
      message: "",
    };

    render(
      <PermissionAlert
        permissionStatus={status}
        onDismiss={mockOnDismiss}
        onReconnect={mockOnReconnect}
      />
    );

    const dismissButton = screen.getByText("Dismiss");
    fireEvent.click(dismissButton);

    expect(mockOnDismiss).toHaveBeenCalledTimes(1);
  });

  it("should call onReconnect when reconnect button is clicked", () => {
    const status: PermissionValidationResult = {
      status: "token_invalid",
      valid: false,
      missing_scopes: [],
      granted_scopes: [],
      issues: ["Token invalid"],
      warnings: [],
      recommendations: ["Reconnect GitHub"],
      message: "",
    };

    render(
      <PermissionAlert
        permissionStatus={status}
        onDismiss={mockOnDismiss}
        onReconnect={mockOnReconnect}
      />
    );

    const reconnectButton = screen.getByRole("button", {
      name: "Reconnect GitHub",
    });
    fireEvent.click(reconnectButton);

    expect(mockOnReconnect).toHaveBeenCalledTimes(1);
  });

  it("should display correct title based on status", () => {
    const statuses: Array<{
      status: PermissionValidationResult["status"];
      expectedTitle: string;
    }> = [
      { status: "token_invalid", expectedTitle: "GitHub Connection Invalid" },
      { status: "missing_scopes", expectedTitle: "Missing GitHub Permissions" },
      { status: "missing_repo_access", expectedTitle: "Limited Repository Access" },
      { status: "missing_org_approval", expectedTitle: "Organization Access Restricted" },
      {
        status: "insufficient_repo_permissions",
        expectedTitle: "Insufficient Repository Permissions",
      },
    ];

    statuses.forEach(({ status, expectedTitle }) => {
      const permStatus: PermissionValidationResult = {
        status,
        valid: false,
        missing_scopes: [],
        granted_scopes: [],
        issues: ["Test issue"],
        warnings: [],
        recommendations: [],
        message: "",
      };

      const { unmount } = render(<PermissionAlert permissionStatus={permStatus} />);

      expect(screen.getByText(expectedTitle)).toBeInTheDocument();

      unmount();
    });
  });

  it("should display close button in corner when onDismiss is provided", () => {
    const status: PermissionValidationResult = {
      status: "missing_scopes",
      valid: false,
      missing_scopes: [],
      granted_scopes: [],
      issues: [],
      warnings: [],
      recommendations: [],
      message: "",
    };

    render(<PermissionAlert permissionStatus={status} onDismiss={mockOnDismiss} />);

    const closeButton = screen.getByLabelText("Dismiss alert");
    expect(closeButton).toBeInTheDocument();

    fireEvent.click(closeButton);
    expect(mockOnDismiss).toHaveBeenCalledTimes(1);
  });

  it("should not display action buttons when callbacks not provided", () => {
    const status: PermissionValidationResult = {
      status: "missing_scopes",
      valid: false,
      missing_scopes: [],
      granted_scopes: [],
      issues: ["Missing permissions"],
      warnings: [],
      recommendations: [],
      message: "",
    };

    render(<PermissionAlert permissionStatus={status} />);

    expect(screen.queryByText("Reconnect GitHub")).not.toBeInTheDocument();
    expect(screen.queryByText("Dismiss")).not.toBeInTheDocument();
  });
});
