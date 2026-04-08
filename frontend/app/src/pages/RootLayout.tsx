import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { MessageSquare, Users, Store, Settings, Plus, ChevronLeft, ChevronRight, LogOut, Camera, Eye, EyeOff } from "lucide-react";
import { useState, useEffect, useCallback, useRef } from "react";
import { uploadUserAvatar } from "@/api/client";
import MemberAvatar from "@/components/MemberAvatar";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import CreateMemberDialog from "@/components/CreateMemberDialog";
import NewChatDialog from "@/components/NewChatDialog";
import { useIsMobile } from "@/hooks/use-mobile";
import { useAppStore } from "@/store/app-store";
import { useAuthStore } from "@/store/auth-store";
import { toast } from "sonner";

const navItems = [
  { to: "/chat", icon: MessageSquare, label: "对话" },
  { to: "/contacts", icon: Users, label: "通讯录" },
  { to: "/marketplace", icon: Store, label: "市场" },
];

const mobileNavItems = [
  ...navItems,
  { to: "/settings", icon: Settings, label: "设置" },
];

// @@@auth-guard — wrapper that shows LoginForm when not authenticated
export default function RootLayout() {
  const token = useAuthStore(s => s.token);
  const setupInfo = useAuthStore(s => s.setupInfo);
  if (!token) return <LoginForm />;
  if (setupInfo) return <SetupNameStep userId={setupInfo.userId} defaultName={setupInfo.defaultName} />;
  return <AuthenticatedLayout />;
}

function AuthenticatedLayout() {
  const authUser = useAuthStore(s => s.user);
  const authLogout = useAuthStore(s => s.logout);

  const location = useLocation();
  const isMobile = useIsMobile();
  const [showCreate, setShowCreate] = useState(false);
  const [createMemberOpen, setCreateMemberOpen] = useState(false);
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [avatarRev, setAvatarRev] = useState(0);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  // @@@profile-avatar-upload — click avatar → file picker → upload → cache bust
  const handleAvatarUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !authUser) return;
    try {
      await uploadUserAvatar(authUser.id, file);
      setAvatarRev(r => r + 1);
      // Persist avatar flag so it survives page refresh
      useAuthStore.setState(s => ({ user: s.user ? { ...s.user, avatar: `avatars/${authUser.id}.png` } : s.user }));
      toast.success("Avatar updated");
    } catch (err) {
      toast.error(`Upload failed: ${err instanceof Error ? err.message : "unknown"}`);
    }
    if (avatarInputRef.current) avatarInputRef.current.value = "";
  }, [authUser]);

  const loadAll = useAppStore((s) => s.loadAll);
  const resetSessionData = useAppStore((s) => s.resetSessionData);
  const lastLoadedUserIdRef = useRef<string | null>(null);

  useEffect(() => {
    const userId = authUser?.id ?? null;
    if (!userId) return;
    if (lastLoadedUserIdRef.current === userId) return;
    // @@@auth-session-reset - switching users in the same SPA process must discard
    // panel caches before reloading, otherwise the next account inherits old
    // members/tasks and the sidebar mixes identities.
    lastLoadedUserIdRef.current = userId;
    resetSessionData();
    void loadAll();
  }, [authUser?.id, loadAll, resetSessionData]);

  const [expanded, setExpanded] = useState(() => {
    const saved = localStorage.getItem("sidebar-expanded");
    return saved ? saved === "true" : false;
  });

  useEffect(() => { localStorage.setItem("sidebar-expanded", String(expanded)); }, [expanded]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && showCreate) setShowCreate(false);
      if ((e.metaKey || e.ctrlKey) && e.key === "b") { e.preventDefault(); setExpanded((prev) => !prev); }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [showCreate]);

  const handleCreateAction = useCallback(async (action: string) => {
    setShowCreate(false);
    switch (action) {
      case "staff": setCreateMemberOpen(true); break;
      case "chat": setNewChatOpen(true); break;
    }
  }, []);

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
    const prevIsChat = prevIsChatRef.current;
    prevIsChatRef.current = isChat;
    if (prevIsChat === isChat) return;

    const syncSidebar = window.setTimeout(() => {
      setExpanded(!isChat);
    }, 0);
    return () => window.clearTimeout(syncSidebar);
  }, [isChat]);

  // Shared nav content
  const renderNavItems = (closeMobile?: () => void) => (
    <>
      {navItems.map((item) => {
        const isActive = location.pathname.startsWith(item.to);
        const labelsVisible = isMobile || showLabels;
        return (
          <NavLink key={item.to} to={item.to} onClick={closeMobile} className="group relative block overflow-visible">
            <div className={`flex items-center ${labelsVisible ? "px-3 gap-3" : "justify-center"} h-10 rounded-xl transition-all duration-fast ${
              isActive ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-muted hover:text-foreground"
            } ${labelsVisible ? "" : "w-10"}`}>
              <item.icon className="w-[18px] h-[18px] shrink-0" />
              {labelsVisible && <span className="text-sm truncate">{item.label}</span>}
            </div>
            {!labelsVisible && !isMobile && (
              <div className="absolute left-14 top-1/2 -translate-y-1/2 px-2 py-1 bg-foreground text-background text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-fast whitespace-nowrap z-50">
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
          {/* @@@outlet-no-route-key - thread switches should not remount the entire
              outlet tree; RootLayout route keys were re-triggering AppLayout
              bootstrap fetches on every /chat/hire/thread/:threadId hop. */}
          <div className="h-full animate-page-in"><Outlet /></div>
        </main>

        {/* Bottom tab bar */}
        <nav className="shrink-0 border-t border-border bg-card flex items-stretch" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
          {mobileNavItems.map((item) => {
            const isActive = location.pathname.startsWith(item.to);
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className="flex-1 flex flex-col items-center justify-center gap-0.5 py-2 transition-colors duration-fast"
                aria-label={item.label}
              >
                <item.icon className={`w-5 h-5 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
                <span className={`text-2xs leading-tight ${isActive ? "text-primary font-semibold" : "text-muted-foreground"}`}>
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
        <aside className={`w-full bg-sidebar flex flex-col py-4 overflow-hidden ${dragging ? "" : "transition-all duration-normal"}`}>
          <div className={`flex items-center ${showLabels ? "px-4 gap-3" : "justify-center"} mb-6`}>
            <img src="/logo.png" alt="Mycel" className="w-8 h-8 rounded-lg shrink-0 object-contain" />
            {showLabels && <span className="text-sm font-semibold text-foreground truncate">Mycel</span>}
          </div>

          <div className={`relative ${showLabels ? "px-3" : "flex justify-center"} mb-4`}>
            <button
              ref={createBtnRef}
              onClick={() => setShowCreate(!showCreate)}
              className={`rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-md hover:shadow-lg hover:scale-105 transition-all duration-fast ${
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
            {/* @@@avatar-popover — Radix Popover for profile + avatar upload + logout */}
            <Popover>
              <PopoverTrigger asChild>
                <button className={`flex items-center ${showLabels ? "px-3 gap-3" : "justify-center"} h-10 mb-1 rounded-xl hover:bg-muted transition-colors duration-fast w-full`}>
                  <MemberAvatar name={authUser?.name || "User"} avatarUrl={(authUser?.avatar || avatarRev > 0) && authUser?.id ? `/api/users/${authUser.id}/avatar` : undefined} size="sm" type="human" rev={avatarRev} />
                  {showLabels && (
                    <div className="min-w-0 flex-1 text-left">
                      <p className="text-xs font-medium text-foreground truncate">{authUser?.name || "User"}</p>
                    </div>
                  )}
                </button>
              </PopoverTrigger>
              <PopoverContent side="top" align="start" className="w-56">
                <div className="flex flex-col items-center gap-3">
                  <div className="relative group/avatar cursor-pointer" onClick={() => avatarInputRef.current?.click()}>
                    <MemberAvatar name={authUser?.name || "User"} avatarUrl={(authUser?.avatar || avatarRev > 0) && authUser?.id ? `/api/users/${authUser.id}/avatar` : undefined} size="lg" type="human" rev={avatarRev} />
                    <div className="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover/avatar:opacity-100 transition-opacity duration-fast flex items-center justify-center">
                      <Camera className="w-5 h-5 text-white" />
                    </div>
                    <input ref={avatarInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" onChange={handleAvatarUpload} />
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-medium">{authUser?.name || "User"}</p>
                  </div>
                  <button
                    onClick={authLogout}
                    className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors duration-fast"
                  >
                    <LogOut className="w-3.5 h-3.5" /> 退出登录
                  </button>
                </div>
              </PopoverContent>
            </Popover>
            <NavLink to="/settings" className="group relative block overflow-visible">
              <div className={`flex items-center ${showLabels ? "px-3 gap-3" : "justify-center"} h-10 rounded-xl transition-all duration-fast ${
                location.pathname.startsWith("/settings") ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-muted hover:text-foreground"
              } ${showLabels ? "" : "w-10"}`}>
                <Settings className="w-[18px] h-[18px] shrink-0" />
                {showLabels && <span className="text-sm">设置</span>}
              </div>
              {!showLabels && (
                <div className="absolute left-14 top-1/2 -translate-y-1/2 px-2 py-1 bg-foreground text-background text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-fast whitespace-nowrap z-50">设置</div>
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
          } transition-colors duration-fast`}
          title="拖拽调整侧栏宽度，双击切换"
        >
          <div className={`w-4 h-8 rounded-full bg-sidebar-border flex items-center justify-center opacity-0 group-hover/handle:opacity-100 ${dragging ? "opacity-100" : ""} transition-opacity duration-fast`}>
            {expanded ? <ChevronLeft className="w-3 h-3 text-muted-foreground" /> : <ChevronRight className="w-3 h-3 text-muted-foreground" />}
          </div>
        </div>
      </div>

      <main className="flex-1 overflow-hidden">
        <div className="h-full animate-page-in"><Outlet /></div>
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
        <button onClick={() => onAction("staff")} className="w-full px-3 py-2 text-left text-sm text-foreground hover:bg-muted transition-colors duration-fast flex items-center gap-2.5">
          <Users className="w-3.5 h-3.5 text-muted-foreground" /> 新建 Agent
        </button>
        <button onClick={() => onAction("chat")} className="w-full px-3 py-2 text-left text-sm text-foreground hover:bg-muted transition-colors duration-fast flex items-center gap-2.5">
          <MessageSquare className="w-3.5 h-3.5 text-muted-foreground" /> 发起会话
        </button>
      </div>
    </>
  );
}

// ── Auth form states ──────────────────────────────────────────────────────
type AuthStep =
  | { type: "login" }
  | { type: "reg_email" }
  | { type: "reg_otp"; email: string; password: string; inviteCode: string };

function AuthCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-sm px-6">{children}</div>
    </div>
  );
}

function AuthHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="text-center mb-8">
      <img src="/logo.png" alt="Mycel" className="w-16 mx-auto mb-4" />
      <h1 className="text-xl font-semibold text-foreground">{title}</h1>
      {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
    </div>
  );
}

export function LoginForm() {
  const [step, setStep] = useState<AuthStep>({ type: "login" });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const login = useAuthStore(s => s.login);
  const sendOtp = useAuthStore(s => s.sendOtp);
  const verifyOtp = useAuthStore(s => s.verifyOtp);
  const completeRegister = useAuthStore(s => s.completeRegister);

  function reset(t: AuthStep) { setStep(t); setError(null); }

  // ── Step: Login ──
  if (step.type === "login") {
    return <LoginStep
      onSubmit={async (identifier, password) => {
        await login(identifier, password);
        navigate("/chat", { replace: true });
      }}
      onSwitch={() => reset({ type: "reg_email" })}
      error={error} setError={setError}
      loading={loading} setLoading={setLoading}
    />;
  }

  // ── Step: Enter email + password + invite code ──
  if (step.type === "reg_email") {
    return <RegEmailStep
      onSubmit={async (email, password, inviteCode) => {
        await sendOtp(email, password, inviteCode);
        setStep({ type: "reg_otp", email, password, inviteCode });
      }}
      onBack={() => reset({ type: "login" })}
      error={error} setError={setError}
      loading={loading} setLoading={setLoading}
    />;
  }

  // ── Step: Enter OTP ──
  const { email, password, inviteCode } = step;
  return <RegOtpStep
    email={email}
    onSubmit={async (token) => {
      const { tempToken } = await verifyOtp(email, token);
      await completeRegister(tempToken, inviteCode);
      // RootLayout will detect setupInfo and render SetupNameStep automatically
    }}
    onResend={async () => {
      await sendOtp(email, password, inviteCode);
    }}
    onBack={() => reset({ type: "reg_email" })}
    error={error} setError={setError}
    loading={loading} setLoading={setLoading}
  />;
}

// ── Sub-steps ────────────────────────────────────────────────────────────

const inputCls = "w-full px-4 py-2.5 rounded-lg border border-border bg-card text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";
const btnCls = "w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50";

function LoginStep({ onSubmit, onSwitch, error, setError, loading, setLoading }: {
  onSubmit: (id: string, pw: string) => Promise<void>;
  onSwitch: () => void;
  error: string | null; setError: (e: string | null) => void;
  loading: boolean; setLoading: (v: boolean) => void;
}) {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  async function handle(e: React.FormEvent) {
    e.preventDefault(); setError(null); setLoading(true);
    try { await onSubmit(identifier, password); }
    catch (err) { setError(err instanceof Error ? err.message : "登录失败"); }
    finally { setLoading(false); }
  }
  return (
    <AuthCard>
      <AuthHeader title="Mycel" subtitle="登录你的账号" />
      <form onSubmit={handle} className="space-y-4">
        <input type="text" name="identifier" aria-label="邮箱或 Mycel ID" placeholder="邮箱或 Mycel ID" value={identifier} onChange={e => setIdentifier(e.target.value)} className={inputCls} required autoComplete="username" />
        <input type="password" name="password" aria-label="密码" placeholder="密码" value={password} onChange={e => setPassword(e.target.value)} className={inputCls} required autoComplete="current-password" />
        {error && <p className="text-xs text-destructive">{error}</p>}
        <button type="submit" disabled={loading} className={btnCls}>{loading ? "请稍候..." : "登录"}</button>
      </form>
      <p className="text-center text-xs text-muted-foreground mt-4">
        没有账号？<button onClick={onSwitch} className="text-primary hover:underline">注册</button>
      </p>
    </AuthCard>
  );
}

function RegEmailStep({ onSubmit, onBack, error, setError, loading, setLoading }: {
  onSubmit: (email: string, password: string, inviteCode: string) => Promise<void>;
  onBack: () => void;
  error: string | null; setError: (e: string | null) => void;
  loading: boolean; setLoading: (v: boolean) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  async function handle(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) { setError("两次输入的密码不一致"); return; }
    setError(null); setLoading(true);
    try { await onSubmit(email, password, inviteCode); }
    catch (err) { setError(err instanceof Error ? err.message : "发送失败"); }
    finally { setLoading(false); }
  }
  return (
    <AuthCard>
      <AuthHeader title="注册账号" subtitle="填写信息，发送验证码" />
      <form onSubmit={handle} className="space-y-4">
        <input type="email" name="email" aria-label="邮箱" placeholder="邮箱" value={email} onChange={e => setEmail(e.target.value)} className={inputCls} required autoComplete="email" autoFocus />
        <PasswordInput value={password} onChange={setPassword} placeholder="设置密码" autoComplete="new-password" name="register-password" ariaLabel="设置密码" />
        <PasswordInput value={confirm} onChange={setConfirm} placeholder="确认密码" autoComplete="new-password" name="register-password-confirm" ariaLabel="确认密码" />
        <input type="text" name="inviteCode" aria-label="邀请码" placeholder="邀请码" value={inviteCode} onChange={e => setInviteCode(e.target.value)} className={inputCls} autoComplete="off" required />
        {error && <p className="text-xs text-destructive">{error}</p>}
        <button type="submit" disabled={loading} className={btnCls}>{loading ? "发送中..." : "发送验证码"}</button>
      </form>
      <p className="text-center text-xs text-muted-foreground mt-4">
        已有账号？<button onClick={onBack} className="text-primary hover:underline">去登录</button>
      </p>
    </AuthCard>
  );
}

function RegOtpStep({ email, onSubmit, onResend, onBack, error, setError, loading, setLoading }: {
  email: string;
  onSubmit: (token: string) => Promise<void>;
  onResend: () => Promise<void>;
  onBack: () => void;
  error: string | null; setError: (e: string | null) => void;
  loading: boolean; setLoading: (v: boolean) => void;
}) {
  const [otp, setOtp] = useState("");
  const [resending, setResending] = useState(false);
  const [resendDone, setResendDone] = useState(false);
  async function handle(e: React.FormEvent) {
    e.preventDefault(); setError(null); setLoading(true);
    try { await onSubmit(otp.trim()); }
    catch (err) { setError(err instanceof Error ? err.message : "验证失败"); }
    finally { setLoading(false); }
  }
  async function handleResend() {
    setError(null); setResending(true); setResendDone(false);
    try { await onResend(); setResendDone(true); }
    catch (err) { setError(err instanceof Error ? err.message : "发送失败"); }
    finally { setResending(false); }
  }
  return (
    <AuthCard>
      <AuthHeader title="验证邮箱" subtitle={`验证码已发送至 ${email}`} />
      <form onSubmit={handle} className="space-y-4">
        <input
          type="text" name="otp" aria-label="6 位验证码" inputMode="numeric" placeholder="6 位验证码"
          value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, ""))}
          maxLength={6} autoComplete="one-time-code" autoFocus
          className={`${inputCls} text-center tracking-widest text-lg font-mono`}
          required
        />
        {error && <p className="text-xs text-destructive">{error}</p>}
        {resendDone && !error && <p className="text-xs text-success">验证码已重新发送</p>}
        <button type="submit" disabled={loading || otp.length < 6} className={btnCls}>
          {loading ? "验证中..." : "确认"}
        </button>
      </form>
      <p className="text-center text-xs text-muted-foreground mt-4">
        没收到？<button onClick={handleResend} disabled={resending || loading} className="text-primary hover:underline">{resending ? "发送中..." : "重新发送"}</button>
        <span className="mx-2 text-border">·</span>
        <button onClick={onBack} className="text-primary hover:underline">修改信息</button>
      </p>
    </AuthCard>
  );
}

function PasswordInput({ value, onChange, placeholder, autoFocus, autoComplete, name, ariaLabel }: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  autoFocus?: boolean;
  autoComplete?: string;
  name?: string;
  ariaLabel?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input
        type={visible ? "text" : "password"}
        name={name}
        aria-label={ariaLabel ?? placeholder}
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
        className={`${inputCls} pr-10`}
        required
        autoComplete={autoComplete}
        autoFocus={autoFocus}
        minLength={6}
      />
      <button
        type="button"
        onClick={() => setVisible(v => !v)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors duration-fast"
        tabIndex={-1}
      >
        {visible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </div>
  );
}


function SetupNameStep({ userId, defaultName }: { userId: string; defaultName: string }) {
  const [name, setName] = useState(defaultName);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const token = useAuthStore(s => s.token);
  const clearSetupInfo = useAuthStore(s => s.clearSetupInfo);

  function done() {
    clearSetupInfo();
    navigate("/chat", { replace: true });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      if (name.trim() && name.trim() !== defaultName) {
        await fetch(`/api/panel/agents/${userId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
          body: JSON.stringify({ name: name.trim() }),
        });
        useAuthStore.setState(s => ({ user: s.user ? { ...s.user, name: name.trim() } : s.user }));
      }
    } finally {
      done();
    }
  }

  return (
    <AuthCard>
      <AuthHeader title="你好！" subtitle="你希望大家怎么称呼你？" />
      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          type="text"
          name="displayName"
          aria-label="显示名称"
          value={name}
          onChange={e => setName(e.target.value)}
          className={inputCls}
          autoFocus
          maxLength={32}
        />
        <button type="submit" disabled={loading} className={btnCls}>
          {loading ? "请稍候..." : "开始使用"}
        </button>
      </form>
      <p className="text-center text-xs text-muted-foreground mt-4">
        <button
          onClick={done}
          className="text-muted-foreground hover:text-foreground hover:underline"
        >
          跳过
        </button>
      </p>
    </AuthCard>
  );
}
