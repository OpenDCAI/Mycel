import { createBrowserRouter, Navigate } from 'react-router-dom';
import RootLayout from './pages/RootLayout';
import AppLayout from './pages/AppLayout';
import ChatPage from './pages/ChatPage';
import NewChatPage from './pages/NewChatPage';
import ThreadsIndexRedirect from './pages/ThreadsIndexRedirect';
import ChatsLayout from './pages/ChatsLayout';
import ChatsEmptyState from './pages/ChatsEmptyState';
import ChatConversationPage from './pages/ChatConversationPage';
import SettingsPage from './pages/SettingsPage';
import MembersPage from './pages/MembersPage';
import AgentDetailPage from './pages/AgentDetailPage';
import TasksPage from './pages/TasksPage';
import MarketplacePage from './pages/MarketplacePage';
import MarketplaceDetailPage from './pages/MarketplaceDetailPage';
import ResourcesPage from './pages/ResourcesPage';
import ConnectionsPage from './pages/ConnectionsPage';

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
            path: ':memberId/new',
            element: <NewChatPage mode="new" />,
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
        path: 'marketplace',
        element: <MarketplacePage />,
      },
      {
        path: 'marketplace/:id',
        element: <MarketplaceDetailPage />,
      },
      {
        path: 'library',
        element: <Navigate to="/marketplace" replace />,
      },
      {
        path: 'connections',
        element: <ConnectionsPage />,
      },
      {
        path: 'settings',
        element: <SettingsPage />,
      },
    ],
  },
]);
