import { useCallback, useState } from "react";
import {
  sendMessage,
} from "../api";
import type { TabType } from "../components/computer-panel/types";


interface AppActionsDeps {
  activeThreadId: string | null;
}

export interface AppActionsState {
  computerOpen: boolean;
  computerTab: TabType;
}

export interface AppActionsSetters {
  setComputerOpen: React.Dispatch<React.SetStateAction<boolean>>;
  setComputerTab: (tab: TabType) => void;
}

export interface AppActionsHandlers {
  handleFocusAgent: () => void;
  handleSendQueueMessage: (message: string) => Promise<void>;
}

export function useAppActions(deps: AppActionsDeps): AppActionsState & AppActionsSetters & AppActionsHandlers {
  const { activeThreadId } = deps;

  const [computerOpen, setComputerOpen] = useState(false);
  const [computerTab, setComputerTab] = useState<TabType>("files");

  const handleFocusAgent = useCallback(() => {
    setComputerTab("agents");
    setComputerOpen(true);
  }, []);

  const handleSendQueueMessage = useCallback(
    async (message: string) => {
      if (!activeThreadId) return;
      // @@@display-builder — no local user entry. Backend emits user_message
      // via display_delta when the steer is consumed (either by before_model
      // in current run, or by _consume_followup_queue as a new run).
      await sendMessage(activeThreadId, message);
    },
    [activeThreadId],
  );

  return {
    computerOpen, computerTab,
    setComputerOpen, setComputerTab,
    handleFocusAgent, handleSendQueueMessage,
  };
}
