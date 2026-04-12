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
  focusedAgentStepId: string | null;
  sidebarCollapsed: boolean;
  searchOpen: boolean;
  sessionsOpen: boolean;
  newThreadOpen: boolean;
}

export interface AppActionsSetters {
  setComputerOpen: React.Dispatch<React.SetStateAction<boolean>>;
  setComputerTab: (tab: TabType) => void;
  setFocusedAgentStepId: (id: string | null) => void;
  setSidebarCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
  setSearchOpen: (open: boolean) => void;
  setSessionsOpen: (open: boolean) => void;
  setNewThreadOpen: (open: boolean) => void;
}

export interface AppActionsHandlers {
  handleFocusAgent: (stepId: string) => void;
  handleSendQueueMessage: (message: string) => Promise<void>;
}

export function useAppActions(deps: AppActionsDeps): AppActionsState & AppActionsSetters & AppActionsHandlers {
  const { activeThreadId } = deps;

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [computerOpen, setComputerOpen] = useState(false);
  const [computerTab, setComputerTab] = useState<TabType>("files");
  const [focusedAgentStepId, setFocusedAgentStepId] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [newThreadOpen, setNewThreadOpen] = useState(false);

  const handleFocusAgent = useCallback((stepId: string) => {
    setFocusedAgentStepId(stepId);
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
    computerOpen, computerTab, focusedAgentStepId,
    sidebarCollapsed, searchOpen, sessionsOpen, newThreadOpen,
    setComputerOpen, setComputerTab, setFocusedAgentStepId,
    setSidebarCollapsed, setSearchOpen, setSessionsOpen, setNewThreadOpen,
    handleFocusAgent, handleSendQueueMessage,
  };
}
