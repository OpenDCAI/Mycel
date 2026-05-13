import React from "react";

import { MONITOR_TOKEN_KEY, MonitorFetchError, readMonitorToken } from "../app/fetch";

export default function ErrorState({ title, error }: { title: string; error: MonitorFetchError }) {
  const [token, setToken] = React.useState(() => readMonitorToken() ?? "");
  const heading = error.status === 401 ? `${title}: Unauthorized` : `${title}: Request failed`;

  function saveToken() {
    const trimmed = token.trim();
    if (!trimmed || typeof window === "undefined") return;
    window.localStorage.setItem(MONITOR_TOKEN_KEY, trimmed);
    window.location.reload();
  }

  function clearToken() {
    if (typeof window === "undefined") return;
    window.localStorage.removeItem(MONITOR_TOKEN_KEY);
    window.location.reload();
  }

  return (
    <div className="page">
      <h1>{heading}</h1>
      <p className="error">{error.message}</p>
      {error.status === 401 && (
        <div className="info-grid">
          <label>
            <strong>Bearer token</strong>
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste JWT token"
            />
          </label>
          <div>
            <button onClick={saveToken} disabled={!token.trim()}>
              Save token and retry
            </button>
            <button onClick={clearToken} style={{ marginLeft: 8 }}>
              Clear saved token
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
