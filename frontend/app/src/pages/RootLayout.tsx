import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { MessageSquare, Users, ListTodo, Library, Settings, Plus, ChevronLeft, ChevronRight } from "lucide-react";
import { useState, useEffect, useCallback, useRef } from "react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import CreateMemberDialog from "@/components/CreateMemberDialog";
import NewChatDialog from "@/components/NewChatDialog";
import { useIsMobile } from "@/hooks/use-mobile";
import { useAppStore } from "@/store/app-store";
import { toast } from "sonner";

const navItems = [
  { to: "/chat", icon: MessageSquare, label: "消息" },
  { to: "/members", icon: Users, label: "成员" },
  { to: "/tasks", icon: ListTodo, label: "任务" },
  { to: "/library", icon: Library, label: "能力库" },
];

const mobileNavItems = [
  ...navItems,
  { to: "/settings", icon: Settings, label: "设置" },
];

export default function RootLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [showCreate, setShowCreate] = useState(false);
  const [createMemberOpen, setCreateMemberOpen] = useState(false);
  const [newChatOpen, setNewChatOpen] = useState(false);

  const userProfile = useAppStore((s) => s.userProfile);
  const loadAll = useAppStore((s) => s.loadAll);
  const storeAddTask = useAppStore((s) => s.addTask);

  useEffect(() => { loadAll(); }, [loadAll]);

  const [expanded, setExpanded] = useState(() => {
    const saved = localStorage.getItem("sidebar-expanded");
    return saved ? saved === "true" : false;
  });

  useEffect(() => { localStorage.setItem("sidebar-expanded", String(expanded)); }, [expanded]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && showCreate) setShowCreate(false);
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [showCreate]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "b") { e.preventDefault(); setExpanded((prev) => !prev); }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleCreateAction = useCallback(async (action: string) => {
    setShowCreate(false);
    switch (action) {
      case "staff": setCreateMemberOpen(true); break;
      case "chat": setNewChatOpen(true); break;
      case "task":
        try {
          await storeAddTask();
          navigate("/tasks");
        } catch (e: unknown) {
          toast.error("创建失败: " + (e instanceof Error ? e.message : String(e)));
        }
        break;
    }
  }, [navigate, storeAddTask]);

  const createBtnRef = useRef<HTMLButtonElement>(null);

  // Drag-to-resize sidebar
  const EXPANDED_W = 200;
  const COLLAPSED_W = 60;
  const SNAP_THRESHOLD = 130;
  const [dragging, setDragging] = useState(false);
  const [dragWidth, setDragWidth] = useState<number | null>(null);
  const dragRef = useRef({ startX: 0, startW: 0 });

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const currentW = expanded ? EXPANDED_W : COLLAPSED_W;
    dragRef.current = { startX: e.clientX, startW: currentW };
    setDragWidth(currentW);
    setDragging(true);
  }, [expanded]);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => {
      const delta = e.clientX - dragRef.current.startX;
      const newW = Math.max(COLLAPSED_W, Math.min(EXPANDED_W, dragRef.current.startW + delta));
      setDragWidth(newW);
    };
    const onUp = () => {
      setDragging(false);
      if (dragWidth !== null) {
        const shouldExpand = dragWidth >= SNAP_THRESHOLD;
        setExpanded(shouldExpand);
      }
      setDragWidth(null);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, [dragging, dragWidth]);

  const isChat = location.pathname.startsWith("/chat");
  const sidebarPx = dragging && dragWidth !== null ? dragWidth : (expanded ? EXPANDED_W : COLLAPSED_W);
  const showLabels = dragging ? (dragWidth !== null && dragWidth >= SNAP_THRESHOLD) : expanded;

  // Auto-collapse sidebar when entering chat, expand when leaving
  const prevIsChatRef = useRef(isChat);
  useEffect(() => {
    if (isChat && !prevIsChatRef.current) {
      setExpanded(false);
    } else if (!isChat && prevIsChatRef.current) {
      setExpanded(true);
    }
    prevIsChatRef.current = isChat;
  }, [isChat]);

  // Shared nav content
  const renderNavItems = (closeMobile?: () => void) => (
    <>
      {navItems.map((item) => {
        const isActive = location.pathname.startsWith(item.to);
        const labelsVisible = isMobile || showLabels;
        return (
          <NavLink key={item.to} to={item.to} onClick={closeMobile} className="group relative block overflow-visible">
            <div className={`flex items-center ${labelsVisible ? "px-3 gap-3" : "justify-center"} h-10 rounded-xl transition-all duration-150 ${
              isActive ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-muted hover:text-foreground"
            } ${labelsVisible ? "" : "w-10"}`}>
              <item.icon className="w-[18px] h-[18px] shrink-0" />
              {labelsVisible && <span className="text-sm truncate">{item.label}</span>}
            </div>
            {!labelsVisible && !isMobile && (
              <div className="absolute left-14 top-1/2 -translate-y-1/2 px-2 py-1 bg-foreground text-background text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50">
                {item.label}
              </div>
            )}
            {isActive && <div className="absolute -left-[4px] top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-primary" />}
          </NavLink>
        );
      })}
    </>
  );

  if (isMobile) {
    return (
      <div className="flex flex-col h-full overflow-hidden bg-background">
        {/* Main content - no top bar, pages have their own headers */}
        <main className="flex-1 overflow-hidden">
          <div key={location.pathname} className="h-full animate-page-in"><Outlet /></div>
        </main>

        {/* Bottom tab bar */}
        <nav className="shrink-0 border-t border-border bg-card flex items-stretch" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
          {mobileNavItems.map((item) => {
            const isActive = location.pathname.startsWith(item.to);
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className="flex-1 flex flex-col items-center justify-center gap-0.5 py-2 transition-colors"
                aria-label={item.label}
              >
                <item.icon className={`w-5 h-5 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
                <span className={`text-[10px] leading-tight ${isActive ? "text-primary font-semibold" : "text-muted-foreground"}`}>
                  {item.label}
                </span>
              </NavLink>
            );
          })}
        </nav>

        <CreateMemberDialog open={createMemberOpen} onOpenChange={setCreateMemberOpen} />
        <NewChatDialog open={newChatOpen} onOpenChange={setNewChatOpen} />
      </div>
    );
  }

  // Desktop layout
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <div className="relative shrink-0 flex z-20" style={{ width: sidebarPx }}>
        <aside className={`w-full bg-sidebar flex flex-col py-4 overflow-hidden ${dragging ? "" : "transition-all duration-200"}`}>
          <div className={`flex items-center ${showLabels ? "px-4 gap-3" : "justify-center"} mb-6`}>
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center shrink-0">
              <span className="text-primary-foreground font-mono font-bold text-xs">L</span>
            </div>
            {showLabels && <span className="text-sm font-semibold text-foreground truncate">Leon</span>}
          </div>

          <div className={`relative ${showLabels ? "px-3" : "flex justify-center"} mb-4`}>
            <button
              ref={createBtnRef}
              onClick={() => setShowCreate(!showCreate)}
              className={`rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-md hover:shadow-lg hover:scale-105 transition-all ${
                showLabels ? "w-full h-9 rounded-lg gap-2" : "w-10 h-10"
              }`}
            >
              <Plus className="w-4 h-4" />
              {showLabels && <span className="text-sm font-medium">新建</span>}
            </button>
            {showCreate && <CreateDropdown btnRef={createBtnRef} showLabels={showLabels} onAction={handleCreateAction} onClose={() => setShowCreate(false)} />}
          </div>

          <div className={`${showLabels ? "mx-4" : "mx-3"} h-px bg-border mb-3`} />

          <nav className={`flex-1 flex flex-col ${showLabels ? "px-2" : "items-center"} gap-0.5 overflow-visible`}>
            {renderNavItems()}
          </nav>

          <div className={`flex flex-col ${showLabels ? "px-2" : "items-center"} gap-0.5`}>
            <div className={`flex items-center ${showLabels ? "px-3 gap-3" : "justify-center"} h-10 mb-1`}>
              <Avatar className="w-7 h-7 shrink-0">
                <AvatarFallback className="text-[10px] font-semibold bg-primary/10 text-primary">{userProfile.initials}</AvatarFallback>
              </Avatar>
              {showLabels && (
                <div className="min-w-0">
                  <p className="text-xs font-medium text-foreground truncate">{userProfile.name}</p>
                  <p className="text-[10px] text-muted-foreground truncate">{userProfile.email}</p>
                </div>
              )}
            </div>
            <NavLink to="/settings" className="group relative block overflow-visible">
              <div className={`flex items-center ${showLabels ? "px-3 gap-3" : "justify-center"} h-10 rounded-xl transition-all duration-150 ${
                location.pathname.startsWith("/settings") ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-muted hover:text-foreground"
              } ${showLabels ? "" : "w-10"}`}>
                <Settings className="w-[18px] h-[18px] shrink-0" />
                {showLabels && <span className="text-sm">设置</span>}
              </div>
              {!showLabels && (
                <div className="absolute left-14 top-1/2 -translate-y-1/2 px-2 py-1 bg-foreground text-background text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50">设置</div>
              )}
              {location.pathname.startsWith("/settings") && <div className="absolute -left-[4px] top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-primary" />}
            </NavLink>
          </div>
        </aside>

        {/* Drag handle on sidebar right edge */}
        <div
          onMouseDown={handleDragStart}
          onDoubleClick={() => setExpanded(!expanded)}
          className={`absolute right-0 top-0 bottom-0 w-[5px] z-30 cursor-col-resize group/handle flex items-center justify-center ${
            dragging ? "bg-primary/20" : "hover:bg-primary/10"
          } transition-colors`}
          title="拖拽调整侧栏宽度，双击切换"
        >
          <div className={`w-4 h-8 rounded-full bg-sidebar-border flex items-center justify-center opacity-0 group-hover/handle:opacity-100 ${dragging ? "opacity-100" : ""} transition-opacity`}>
            {expanded ? <ChevronLeft className="w-3 h-3 text-muted-foreground" /> : <ChevronRight className="w-3 h-3 text-muted-foreground" />}
          </div>
        </div>
      </div>

      <main className="flex-1 overflow-hidden">
        <div key={location.pathname} className="h-full animate-page-in"><Outlet /></div>
      </main>
      <CreateMemberDialog open={createMemberOpen} onOpenChange={setCreateMemberOpen} />
      <NewChatDialog open={newChatOpen} onOpenChange={setNewChatOpen} />
    </div>
  );
}

function CreateDropdown({
  btnRef,
  showLabels,
  onAction,
  onClose,
}: {
  btnRef: React.RefObject<HTMLButtonElement | null>;
  showLabels: boolean;
  onAction: (action: string) => void;
  onClose: () => void;
}) {
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    const el = btnRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (showLabels) {
      setPos({ top: rect.bottom + 4, left: rect.left });
    } else {
      setPos({ top: rect.top, left: rect.right + 8 });
    }
  }, [btnRef, showLabels]);

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div
        className="fixed z-50 w-48 bg-card border border-border rounded-lg shadow-lg py-1.5 animate-slide-in"
        style={{ top: pos.top, left: pos.left }}
      >
        <button onClick={() => onAction("staff")} className="w-full px-3 py-2 text-left text-sm text-foreground hover:bg-muted transition-colors flex items-center gap-2.5">
          <Users className="w-3.5 h-3.5 text-muted-foreground" /> 新建成员
        </button>
        <button onClick={() => onAction("chat")} className="w-full px-3 py-2 text-left text-sm text-foreground hover:bg-muted transition-colors flex items-center gap-2.5">
          <MessageSquare className="w-3.5 h-3.5 text-muted-foreground" /> 发起会话
        </button>
        <button onClick={() => onAction("task")} className="w-full px-3 py-2 text-left text-sm text-foreground hover:bg-muted transition-colors flex items-center gap-2.5">
          <ListTodo className="w-3.5 h-3.5 text-muted-foreground" /> 新建任务
        </button>
      </div>
    </>
  );
}