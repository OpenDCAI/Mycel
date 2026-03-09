import { createBrowserRouter, Navigate } from 'react-router-dom';
import RootLayout from './pages/RootLayout';
import AppLayout from './pages/AppLayout';
import ChatPage from './pages/ChatPage';
import NewChatPage from './pages/NewChatPage';
import SettingsPage from './pages/SettingsPage';
import MembersPage from './pages/MembersPage';
import AgentDetailPage from './pages/AgentDetailPage';
import TasksPage from './pages/TasksPage';
import LibraryPage from './pages/LibraryPage';
import ResourcesPage from './pages/ResourcesPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/chat" replace />,
  },
  {
    path: '/',
    element: <RootLayout />,
    children: [
      {
        path: 'chat',
        element: <AppLayout />,
        children: [
          {
            index: true,
            element: <Navigate to="/chat/leon" replace />,
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
