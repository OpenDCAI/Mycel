import { useCallback } from "react";
import { getThreadTerminal } from "../../api";

interface UseRemoteWorkspaceRootOptions {
  threadId: string | null;
  isRemote: boolean;
}

interface RemoteWorkspaceRootResult {
  refreshWorkspaceRoot: () => Promise<string | undefined>;
}

export function useRemoteWorkspaceRoot({ threadId, isRemote }: UseRemoteWorkspaceRootOptions): RemoteWorkspaceRootResult {
  const refreshWorkspaceRoot = useCallback(async (): Promise<string | undefined> => {
    if (!threadId) return undefined;
    if (!isRemote) return undefined;

    const terminal = await getThreadTerminal(threadId);
    return terminal.cwd;
  }, [threadId, isRemote]);

  return { refreshWorkspaceRoot };
}
