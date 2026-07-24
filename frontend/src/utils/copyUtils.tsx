import React from "react";

// Utility function to copy text to clipboard
export const copyToClipboard = async (
  text: string,
  onSuccess?: () => void,
  onError?: (err: unknown) => void
): Promise<void> => {
  try {
    if (navigator.clipboard && globalThis.isSecureContext) {
      // Use modern clipboard API
      await navigator.clipboard.writeText(text);
    } else {
      // Fallback for older browsers or non-secure contexts
      const textArea = document.createElement("textarea");
      textArea.value = text;
      textArea.style.position = "fixed";
      textArea.style.left = "-999999px";
      textArea.style.top = "-999999px";
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      document.execCommand("copy");
      textArea.remove();
    }

    if (onSuccess) {
      onSuccess();
    }
  } catch (err) {
    console.error("Failed to copy text: ", err);
    if (onError) {
      onError(err);
    }
  }
};

// Props interface for CopyButton
interface CopyButtonProps {
  textToCopy: string;
  className?: string;
  title?: string;
}

// Copy button component with visual feedback
export const CopyButton: React.FC<CopyButtonProps> = ({
  textToCopy,
  className = "",
  title = "Copy to clipboard",
}) => {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    await copyToClipboard(
      textToCopy,
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000); // Reset after 2 seconds
      },
      (err) => {
        console.error("Copy failed:", err);
        // Could show error toast here
      }
    );
  };

  return (
    <button
      onClick={handleCopy}
      className={`copy-button ${className} ${copied ? "copied" : ""}`}
      title={copied ? "Copied!" : title}
      type="button"
    >
      {copied ? "✓" : "📋"}
    </button>
  );
};
