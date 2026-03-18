import { createBrowserRouter, Navigate, useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { useAuthStore } from './store/auth-store';
import RootLayout from './pages/RootLayout';
import AppLayout from './pages/AppLayout';
import ChatPage from './pages/ChatPage';
import NewChatPage from './pages/NewChatPage';
import ChatsLayout from './pages/ChatsLayout';
import ChatsEmptyState from './pages/ChatsEmptyState';
import ChatConversationPage from './pages/ChatConversationPage';
import SettingsPage from './pages/SettingsPage';
import MembersPage from './pages/MembersPage';
import AgentDetailPage from './pages/AgentDetailPage';
import TasksPage from './pages/TasksPage';
import LibraryPage from './pages/LibraryPage';
import ResourcesPage from './pages/ResourcesPage';

/** Redirect /threads → /threads/{owned agent name} dynamically. */
function ThreadsIndexRedirect() {
  const agent = useAuthStore(s => s.agent);
  const navigate = useNavigate();
  useEffect(() => {
    const name = agent?.name || "leon";
    navigate(`/threads/${encodeURIComponent(name)}`, { replace: true });
  }, [agent, navigate]);
  return null;
}

export const router = createBrowserRouter([
  // Old /chat/* URLs → redirect to /threads
  {
    path: '/chat/*',
    element: <Navigate to="/threads" replace />,
  },
  {
    path: '/',
    element: <RootLayout />,
    children: [
      {
        index: true,
        element: <Navigate to="/threads" replace />,
      },
      {
        path: 'threads',
        element: <AppLayout />,
        children: [
          {
            index: true,
            element: <ThreadsIndexRedirect />,
          },
          {
            path: ':memberId',
            element: <NewChatPage />,
          },
          {
            path: ':memberId/:threadId',
            element: <ChatPage />,
          },
        ],
      },
      {
        path: 'chats',
        element: <ChatsLayout />,
        children: [
          {
            index: true,
            element: <ChatsEmptyState />,
          },
          {
            path: ':chatId',
            element: <ChatConversationPage />,
          },
        ],
      },
      {
        path: 'members',
        element: <MembersPage />,
      },
      {
        path: 'members/:id',
        element: <AgentDetailPage />,
      },
      {
        path: 'tasks',
        element: <TasksPage />,
      },
      {
        path: 'resources',
        element: <ResourcesPage />,
      },
      {
        path: 'library',
        element: <LibraryPage />,
      },
      {
        path: 'settings',
        element: <SettingsPage />,
      },
    ],
  },
]);
