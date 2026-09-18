import React from "react";
import { getDocsUrl } from "../help/helpLinks";

/**
 * Renders a PAT error, linking the HTTPS setup guide when the backend's
 * non-local-HTTP guard is what rejected it.
 *
 * The same 400 comes from login, token test and token save, and the usual
 * cause is a reverse proxy that did not forward X-Forwarded-Proto — something
 * the admin can only fix with the guide. The wording keyed off here is pinned
 * by backend/tests/test_auth_http_security.py.
 */
const GUIDE_SENTENCE = "Setup guide:";

interface TokenErrorMessageProps {
  readonly message: string;
}

export default function TokenErrorMessage({ message }: TokenErrorMessageProps): React.ReactElement {
  const isInsecureHttp = message.includes("non-local HTTP");
  // The message carries the URL for API and log readers; in the UI the link
  // below replaces it rather than showing the same address twice.
  const text = isInsecureHttp ? message.split(GUIDE_SENTENCE)[0].trim() : message;

  return (
    <>
      {text}
      {isInsecureHttp && (
        <a
          className="mt-1 block font-medium underline"
          href={getDocsUrl("httpsSetup")}
          rel="noreferrer"
          target="_blank"
        >
          HTTPS setup guide →
        </a>
      )}
    </>
  );
}
