export type TasksTab = "tasks" | "cron";

export function resolveTasksTab(search: string | URLSearchParams): TasksTab {
  const params = typeof search === "string" ? new URLSearchParams(search) : search;
  return params.get("tab") === "scheduled" ? "cron" : "tasks";
}

export function tasksHref(tab: TasksTab): string {
  return tab === "cron" ? "/tasks?tab=scheduled" : "/tasks";
}

export function isTasksNavActive(pathname: string, search: string, tab: TasksTab): boolean {
  if (!pathname.startsWith("/tasks")) return false;
  return resolveTasksTab(search) === tab;
}
