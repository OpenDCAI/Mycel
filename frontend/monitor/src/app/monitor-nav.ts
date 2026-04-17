export type MonitorNavItem = {
  to: string;
  label: string;
  matchPrefixes?: string[];
  eyebrow: string;
};

export const monitorNav: readonly MonitorNavItem[] = [
  { to: "/dashboard", label: "Dashboard", eyebrow: "Overview" },
  { to: "/resources", label: "Resources", eyebrow: "Runtime", matchPrefixes: ["/resources", "/providers", "/runtimes"] },
  { to: "/sandboxes", label: "Sandboxes", eyebrow: "Runtime", matchPrefixes: ["/sandboxes", "/operations"] },
  { to: "/sandbox-configs", label: "Sandbox Configs", eyebrow: "Config" },
  { to: "/threads", label: "Threads", eyebrow: "Workbench", matchPrefixes: ["/threads"] },
  { to: "/evaluation", label: "Evaluation", eyebrow: "Operators", matchPrefixes: ["/evaluation"] },
];

export function resolveMonitorNav(pathname: string): MonitorNavItem {
  return (
    monitorNav.find(
      (item) =>
        pathname === item.to ||
        item.matchPrefixes?.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)),
    ) ??
    monitorNav[0]
  );
}
