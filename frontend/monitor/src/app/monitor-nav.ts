export type MonitorNavItem = {
  to: string;
  label: string;
  matchPrefix?: string;
  eyebrow: string;
};

export const monitorNav: readonly MonitorNavItem[] = [
  { to: "/dashboard", label: "Dashboard", eyebrow: "Overview" },
  { to: "/resources", label: "Resources", eyebrow: "Runtime" },
  { to: "/leases", label: "Leases", eyebrow: "Runtime" },
  { to: "/evaluation", label: "Evaluation", eyebrow: "Operators" },
];
