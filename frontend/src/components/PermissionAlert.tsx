import React from "react";
import { PermissionValidationResult } from "../api/user";

interface PermissionAlertProps {
  permissionStatus: PermissionValidationResult;
  onDismiss?: () => void;
  onReconnect?: () => void;
}

export const PermissionAlert: React.FC<PermissionAlertProps> = ({
  permissionStatus,
  onDismiss,
  onReconnect,
}) => {
  const isGitHubApp = permissionStatus.details?.auth_type === "github_app";
  const hasWarnings = (permissionStatus.warnings?.length ?? 0) > 0;

  // Don't show alert when permissions are valid and there are no warnings to surface
  if (permissionStatus.valid && !hasWarnings) {
    return null;
  }

  const getSeverityColor = (status: string): string => {
    switch (status) {
      case "token_invalid":
      case "missing_scopes":
        return "bg-red-50 border-red-200 text-red-900";
      case "missing_repo_access":
      case "insufficient_repo_permissions":
        return "bg-orange-50 border-orange-200 text-orange-900";
      case "missing_org_approval":
        return "bg-yellow-50 border-yellow-200 text-yellow-900";
      default:
        return "bg-gray-50 border-gray-200 text-gray-900";
    }
  };

  const getSeverityIcon = (status: string): string => {
    switch (status) {
      case "token_invalid":
      case "missing_scopes":
        return "🚫";
      case "missing_repo_access":
      case "insufficient_repo_permissions":
        return "⚠️";
      case "missing_org_approval":
        return "🔒";
      default:
        return "ℹ️";
    }
  };

  const getTitle = (status: string): string => {
    switch (status) {
      case "token_invalid":
        return "GitHub Connection Invalid";
      case "missing_scopes":
        return isGitHubApp
          ? "GitHub App Permission Issue"
          : "Missing GitHub Permissions";
      case "missing_repo_access":
        return isGitHubApp
          ? "GitHub App Repository Access Issue"
          : "Limited Repository Access";
      case "missing_org_approval":
        return "Organization Access Restricted";
      case "insufficient_repo_permissions":
        return "Insufficient Repository Permissions";
      default:
        return "GitHub Access Issue";
    }
  };

  return (
    <div
      className={`mb-4 border rounded-lg p-4 ${getSeverityColor(
        permissionStatus.status
      )}`}
      role="alert"
    >
      <div className="flex items-start">
        <div className="flex-shrink-0 text-2xl mr-3" aria-hidden="true">
          {getSeverityIcon(permissionStatus.status)}
        </div>
        <div className="flex-1">
          <h3 className="text-lg font-semibold mb-2">
            {getTitle(permissionStatus.status)}
          </h3>

          {/* Issues */}
          {permissionStatus.issues && permissionStatus.issues.length > 0 && (
            <div className="mb-3">
              <p className="font-medium mb-1">Issues:</p>
              <ul className="list-disc list-inside space-y-1">
                {permissionStatus.issues.map((issue, idx) => (
                  <li key={idx} className="text-sm">
                    {issue}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Warnings */}
          {permissionStatus.warnings && permissionStatus.warnings.length > 0 && (
            <div className="mb-3">
              <p className="font-medium mb-1">Warnings:</p>
              <ul className="list-disc list-inside space-y-1">
                {permissionStatus.warnings.map((warning, idx) => (
                  <li key={idx} className="text-sm">
                    {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Missing Scopes - only show for OAuth sessions */}
          {!isGitHubApp &&
            permissionStatus.missing_scopes &&
            permissionStatus.missing_scopes.length > 0 && (
              <div className="mb-3">
                <p className="font-medium mb-1">Missing Permissions:</p>
                <div className="flex flex-wrap gap-2">
                  {permissionStatus.missing_scopes.map((scope, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center px-2 py-1 rounded text-xs font-mono bg-white bg-opacity-60"
                    >
                      {scope}
                    </span>
                  ))}
                </div>
              </div>
            )}

          {/* Recommendations */}
          {permissionStatus.recommendations &&
            permissionStatus.recommendations.length > 0 && (
              <div className="mb-3">
                <p className="font-medium mb-1">How to Fix:</p>
                <ol className="list-decimal list-inside space-y-1">
                  {permissionStatus.recommendations.map((rec, idx) => (
                    <li key={idx} className="text-sm">
                      {rec}
                    </li>
                  ))}
                </ol>
              </div>
            )}

          {/* Action Buttons */}
          <div className="flex gap-2 mt-4">
            {onReconnect && (
              <button
                onClick={onReconnect}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors text-sm font-medium"
              >
                {isGitHubApp ? "Reconnect App" : "Reconnect GitHub"}
              </button>
            )}
            {onDismiss && (
              <button
                onClick={onDismiss}
                className="px-4 py-2 bg-white bg-opacity-60 rounded hover:bg-opacity-80 transition-colors text-sm font-medium"
              >
                Dismiss
              </button>
            )}
          </div>
        </div>

        {/* Close button in corner */}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="flex-shrink-0 ml-2 text-gray-400 hover:text-gray-600"
            aria-label="Dismiss alert"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
};

export default PermissionAlert;
