import { useState, useEffect, useCallback } from 'react';
import type { UseThreadStreamResult } from './use-thread-stream';
import type { StreamEvent } from '../api/types';

export interface BackgroundTask {
  task_id: string;
  task_type: 'bash' | 'agent';
  status: 'running' | 'completed' | 'error';
  command_line?: string;
  description?: string;
  exit_code?: number;
  error?: string;
}

interface UseBackgroundTasksProps {
  threadId: string;
  subscribe: UseThreadStreamResult["subscribe"];
}

interface BackgroundTaskEventData {
  background: true;
  task_id: string;
  task_type?: BackgroundTask["task_type"];
  command_line?: string;
  description?: string;
}

const threadTasksInflight = new Map<string, Promise<BackgroundTask[]>>();

function isBackgroundTaskEventData(data: unknown): data is BackgroundTaskEventData {
  if (!data || typeof data !== "object") return false;
  const value = data as Record<string, unknown>;
  return value.background === true && typeof value.task_id === "string";
}

function isActiveThreadRoute(threadId: string): boolean {
  const path = window.location.pathname.replace(/\/+$/, "");
  return path.startsWith("/chat/hire/thread/") && path.endsWith(`/${encodeURIComponent(threadId)}`);
}

function loadThreadTasks(threadId: string): Promise<BackgroundTask[]> {
  const existing = threadTasksInflight.get(threadId);
  if (existing) return existing;
  // @@@tasks-inflight-dedup - React StrictMode remounts the page in dev.
  // Reuse the first thread task fetch so the dev switch hot path does not
  // double-hit /tasks before the first response lands.
  const pending = fetch(`/api/threads/${threadId}/tasks`)
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(response.statusText || `HTTP ${response.status}`);
      }
      return response.json() as Promise<BackgroundTask[]>;
    })
    .finally(() => {
      threadTasksInflight.delete(threadId);
    });
  threadTasksInflight.set(threadId, pending);
  return pending;
}

export function useBackgroundTasks({ threadId, subscribe }: UseBackgroundTasksProps) {
  const [tasks, setTasks] = useState<BackgroundTask[]>([]);

  // 从 API 获取任务列表
  const fetchTasks = useCallback(async () => {
    try {
      const data = await loadThreadTasks(threadId);
      setTasks(data);
    } catch (err) {
      // @@@background-tasks-route-teardown - browser navigation can leave the
      // old thread task fetch resolving after the chat page already moved to a
      // different route. Only log if this thread page is still active.
      if (!isActiveThreadRoute(threadId)) return;
      console.error('[BackgroundTasks] Error fetching tasks:', err);
    }
  }, [threadId]);

  // 监听 SSE 事件
  useEffect(() => {
    const unsubscribe = subscribe((event: StreamEvent) => {
      // 只处理 background task 事件
      if (!isBackgroundTaskEventData(event.data)) return;
      const data = event.data;

      if (event.type === 'task_start') {
        // Optimistic update
        setTasks(prev => [...prev, {
          task_id: data.task_id,
          task_type: data.task_type || 'agent',
          status: 'running',
          command_line: data.command_line,
          description: data.description
        }]);
      } else if (event.type === 'task_done' || event.type === 'task_error') {
        // Re-fetch 获取最新状态
        fetchTasks();
      }
    });

    return unsubscribe;
  }, [subscribe, fetchTasks]);

  // 初始加载
  useEffect(() => {
    let cancelled = false;
    void loadThreadTasks(threadId)
      .then((data) => {
        if (!cancelled) setTasks(data);
      })
      .catch((err: unknown) => {
        if (cancelled || !isActiveThreadRoute(threadId)) return;
        console.error('[BackgroundTasks] Error fetching tasks:', err);
      });
    return () => {
      cancelled = true;
    };
  }, [threadId]);

  const getTask = useCallback((taskId: string) => {
    return tasks.find(t => t.task_id === taskId);
  }, [tasks]);

  return { tasks, getTask, refresh: fetchTasks };
}
