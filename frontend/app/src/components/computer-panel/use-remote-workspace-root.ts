import { useCallback } from "react";
import { getThreadFileChannel } from "../../api";

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

    const channel = await getThreadFileChannel(threadId);
    return channel.workspace_path;
  }, [threadId, isRemote]);

  return { refreshWorkspaceRoot };
}
