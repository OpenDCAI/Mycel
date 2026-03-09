export const CAPABILITY_LABELS: Record<string, string> = {
  filesystem: "文件",
  terminal: "终端",
  metrics: "指标",
  screenshot: "截屏",
  web: "Web",
  process: "进程",
  hooks: "Hook",
  snapshot: "快照",
};

export const CAPABILITY_KEYS = [
  "filesystem",
  "terminal",
  "metrics",
  "screenshot",
  "web",
  "process",
  "hooks",
  "snapshot",
] as const;
