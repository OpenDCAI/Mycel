export const CAPABILITY_LABELS: Record<string, string> = {
  filesystem: "文件",
  terminal: "终端",
  metrics: "指标",
  screenshot: "截屏",
  web: "Web",
  process: "进程",
  hooks: "Hook",
  mount: "挂载",
};

export const CAPABILITY_KEYS = [
  "filesystem",
  "terminal",
  "metrics",
  "screenshot",
  "web",
  "process",
  "hooks",
  "mount",
] as const;
