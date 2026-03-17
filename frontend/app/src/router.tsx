import { createBrowserRouter, Navigate } from 'react-router-dom';
import RootLayout from './pages/RootLayout';
import AppLayout from './pages/AppLayout';
import ChatPage from './pages/ChatPage';
import ChatsLayout from './pages/ChatsLayout';
import ChatsEmptyState from './pages/ChatsEmptyState';
import ChatConversationPage from './pages/ChatConversationPage';
import WorkspaceLanding from './pages/WorkspaceLanding';
import SettingsPage from './pages/SettingsPage';
import MembersPage from './pages/MembersPage';
import AgentDetailPage from './pages/AgentDetailPage';
import TasksPage from './pages/TasksPage';
import LibraryPage from './pages/LibraryPage';
import ResourcesPage from './pages/ResourcesPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/threads" replace />,
  },
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
        path: 'threads',
        element: <AppLayout />,
        children: [
          {
            index: true,
            element: <WorkspaceLanding />,
          },
          {
            path: ':threadId',
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
