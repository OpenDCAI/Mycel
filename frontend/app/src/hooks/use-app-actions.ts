import { useCallback, useState } from "react";
import {
  sendMessage,
  type ChatEntry,
} from "../api";
import type { TabType } from "../components/computer-panel/types";

function makeId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

interface AppActionsDeps {
  activeThreadId: string | null;
  setEntries: React.Dispatch<React.SetStateAction<ChatEntry[]>>;
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
  const { activeThreadId, setEntries } = deps;

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [computerOpen, setComputerOpen] = useState(false);
  const [computerTab, setComputerTab] = useState<TabType>("terminal");
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
      const userEntry: ChatEntry = { id: makeId("user"), role: "user", content: message, timestamp: Date.now() };
      setEntries((prev) => [...prev, userEntry]);
      // Server auto-routes: ACTIVE → steer, IDLE → new run
      await sendMessage(activeThreadId, message);
    },
    [activeThreadId, setEntries],
  );

  return {
    computerOpen, computerTab, focusedAgentStepId,
    sidebarCollapsed, searchOpen, sessionsOpen, newThreadOpen,
    setComputerOpen, setComputerTab, setFocusedAgentStepId,
    setSidebarCollapsed, setSearchOpen, setSessionsOpen, setNewThreadOpen,
    handleFocusAgent, handleSendQueueMessage,
  };
}
