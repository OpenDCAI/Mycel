type PortEnv = Partial<
  Record<"LEON_BACKEND_PORT" | "LEON_MONITOR_BACKEND_PORT" | "LEON_MONITOR_PORT" | "LEON_MONITOR_PREVIEW_PORT", string>
>;

type WorktreePortReader = (key: string, defaultPort: string) => string;

type ResolveMonitorPortsOptions = {
  env: PortEnv;
  getWorktreePort: WorktreePortReader;
};

export function resolveMonitorPorts(options: ResolveMonitorPortsOptions) {
  const backendPort = options.env.LEON_BACKEND_PORT || options.getWorktreePort("worktree.ports.backend", "8001");

  return {
    backendPort,
    monitorBackendPort: options.env.LEON_MONITOR_BACKEND_PORT || backendPort,
    devPort: parseInt(
      options.env.LEON_MONITOR_PORT || options.getWorktreePort("worktree.ports.monitor-frontend", "5174"),
      10,
    ),
    previewPort: parseInt(
      options.env.LEON_MONITOR_PREVIEW_PORT || options.getWorktreePort("worktree.ports.monitor-preview", "4174"),
      10,
    ),
  };
}
