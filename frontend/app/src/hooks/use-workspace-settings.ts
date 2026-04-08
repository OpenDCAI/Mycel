import { useCallback, useEffect, useState } from "react";

interface UserSettings {
  default_workspace: string | null;
  recent_workspaces: string[];
  default_model: string;
  enabled_models: string[];
}

function isActiveNewChatRoute(): boolean {
  const path = window.location.pathname.replace(/\/+$/, "");
  return path.startsWith("/chat/hire");
}

export function useWorkspaceSettings() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [loading, setLoading] = useState(true);

  const loadSettings = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch("/api/settings", { signal });
      if (response.ok) {
        const data = await response.json();
        setSettings(data);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      // @@@workspace-settings-route-teardown - this hook currently powers the
      // new-chat hire flow. If navigation already left /chat/hire, a failed
      // settings load is stale UI noise and should not be surfaced.
      if (!isActiveNewChatRoute()) return;
      console.error("Failed to load settings:", err);
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, []);

  async function setDefaultWorkspace(workspace: string): Promise<void> {
    const response = await fetch("/api/settings/workspace", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace }),
    });

    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || "Failed to set workspace");
    }

    await loadSettings();
  }

  async function addRecentWorkspace(workspace: string): Promise<void> {
    try {
      await fetch("/api/settings/workspace/recent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace }),
      });
      await loadSettings();
    } catch (err) {
      console.error("Failed to add recent workspace:", err);
    }
  }

  useEffect(() => {
    const ac = new AbortController();
    void loadSettings(ac.signal);
    return () => ac.abort();
  }, [loadSettings]);

  return {
    settings,
    loading,
    setDefaultWorkspace,
    addRecentWorkspace,
    refreshSettings: loadSettings,
    hasWorkspace: settings?.default_workspace != null,
  };
}
