import { createBrowserRouter, Navigate } from 'react-router-dom';
import RootLayout from './pages/RootLayout';
import SettingsPage from './pages/SettingsPage';
import MarketplacePage from './pages/MarketplacePage';
import MarketplaceDetailPage from './pages/MarketplaceDetailPage';
import LibraryItemDetailPage from './pages/LibraryItemDetailPage';

// Lazy imports for new layout components
import ChatLayout from './pages/chat/ChatLayout';
import ContactsLayout from './pages/contacts/ContactsLayout';

// Legacy pages reused in new routes
import ChatPage from './pages/ChatPage';
import NewChatPage from './pages/NewChatPage';
import ChatConversationPage from './pages/ChatConversationPage';
import AgentDetailPage from './pages/AgentDetailPage';
import MembersPage from './pages/MembersPage';

export const router = createBrowserRouter([
  // Legacy redirects
  { path: '/threads', element: <Navigate to="/chat" replace /> },
  { path: '/threads/*', element: <Navigate to="/chat" replace /> },
  { path: '/chats', element: <Navigate to="/chat" replace /> },
  { path: '/chats/*', element: <Navigate to="/chat" replace /> },
  { path: '/members', element: <Navigate to="/contacts" replace /> },
  { path: '/members/*', element: <Navigate to="/contacts" replace /> },
  { path: '/tasks', element: <Navigate to="/chat" replace /> },
  { path: '/resources', element: <Navigate to="/marketplace" replace /> },
  { path: '/invite-codes', element: <Navigate to="/settings" replace /> },
  {
    path: '/',
    element: <RootLayout />,
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      {
        path: 'chat',
        element: <ChatLayout />,
        children: [
          { index: true, element: null },
          { path: 'hire/:memberId/:threadId', element: <ChatPage /> },
          { path: 'hire/:memberId', element: <NewChatPage /> },
          { path: 'visit/:chatId', element: <ChatConversationPage /> },
        ],
      },
      {
        path: 'contacts',
        element: <ContactsLayout />,
        children: [
          { index: true, element: <MembersPage /> },
          { path: 'agents/:id', element: <AgentDetailPage /> },
        ],
      },
      { path: 'marketplace', element: <MarketplacePage /> },
      { path: 'marketplace/:id', element: <MarketplaceDetailPage /> },
      { path: 'library/:type/:id', element: <LibraryItemDetailPage /> },
      { path: 'library', element: <Navigate to="/marketplace" replace /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
]);
