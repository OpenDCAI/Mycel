import { Folder, Settings as SettingsIcon } from "lucide-react";
import { useState } from "react";
import WorkspaceSetupModal from "./WorkspaceSetupModal";
import { useWorkspaceSettings } from "../hooks/use-workspace-settings";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

export default function SettingsPanel() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [workspaceModalOpen, setWorkspaceModalOpen] = useState(false);
  const { settings, refreshSettings } = useWorkspaceSettings();

  async function handleWorkspaceSet(_workspace: string) {
    await refreshSettings();
    setWorkspaceModalOpen(false);
    setSettingsOpen(false);
  }

  return (
    <>
      <Popover open={settingsOpen} onOpenChange={setSettingsOpen}>
        <PopoverTrigger asChild>
          <button
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <SettingsIcon className="w-4 h-4" />
          </button>
        </PopoverTrigger>

        <PopoverContent align="end" sideOffset={8} className="w-72 p-0">
          {/* Workspace Section */}
          <div className="px-4 py-2">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
              工作区设置
            </div>
            <button
              onClick={() => {
                setWorkspaceModalOpen(true);
                setSettingsOpen(false);
              }}
              className="w-full flex items-center gap-3 py-2 hover:bg-accent rounded-lg px-2 -mx-2"
            >
              <Folder className="w-4 h-4 text-muted-foreground" />
              <div className="text-left flex-1">
                <div className="text-sm">默认工作区</div>
                <div className="text-[11px] text-muted-foreground mt-0.5 truncate">
                  {settings?.default_workspace || "未设置"}
                </div>
              </div>
            </button>
          </div>
        </PopoverContent>
      </Popover>

      <WorkspaceSetupModal
        open={workspaceModalOpen}
        onClose={() => setWorkspaceModalOpen(false)}
        onWorkspaceSet={handleWorkspaceSet}
      />
    </>
  );
}
