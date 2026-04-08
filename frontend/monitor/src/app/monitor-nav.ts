export type MonitorNavItem = {
  to: string;
  label: string;
  matchPrefix?: string;
  eyebrow: string;
};

export const monitorNav: readonly MonitorNavItem[] = [
  { to: "/dashboard", label: "Dashboard", eyebrow: "Overview" },
  { to: "/threads", label: "Threads", matchPrefix: "/thread/", eyebrow: "Runtime" },
  { to: "/resources", label: "Resources", eyebrow: "Runtime" },
  { to: "/leases", label: "Leases", matchPrefix: "/lease/", eyebrow: "Runtime" },
  { to: "/diverged", label: "Diverged", eyebrow: "Signals" },
  { to: "/events", label: "Events", matchPrefix: "/event/", eyebrow: "Signals" },
];
