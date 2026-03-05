import { useState, useEffect, useCallback } from 'react';
import { useThreadStream } from './use-thread-stream';
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
  loading: boolean;
  refreshThreads: () => Promise<void>;
}

export function useBackgroundTasks({ threadId, loading, refreshThreads }: UseBackgroundTasksProps) {
  const [tasks, setTasks] = useState<BackgroundTask[]>([]);
  const { subscribe } = useThreadStream(threadId, { loading, refreshThreads });

  // 从 API 获取任务列表
  const fetchTasks = useCallback(async () => {
    try {
      const response = await fetch(`/api/threads/${threadId}/tasks`);
      if (!response.ok) {
        console.error('[BackgroundTasks] Failed to fetch tasks:', response.statusText);
        return;
      }
      const data = await response.json();
      setTasks(data);
    } catch (err) {
      console.error('[BackgroundTasks] Error fetching tasks:', err);
    }
  }, [threadId]);

  // 监听 SSE 事件
  useEffect(() => {
    const unsubscribe = subscribe((event: StreamEvent) => {
      const data = event.data as any;

      // 只处理 background task 事件
      const isBackgroundTask = data?.background === true;
      if (!isBackgroundTask) return;

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
    fetchTasks();
  }, [fetchTasks]);

  const getTask = useCallback((taskId: string) => {
    return tasks.find(t => t.task_id === taskId);
  }, [tasks]);

  return { tasks, getTask, refresh: fetchTasks };
}
