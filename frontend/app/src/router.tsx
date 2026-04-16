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
import AgentsPage from './pages/AgentsPage';
import ContactDetailPage from './pages/contacts/ContactDetailPage';

export const router = createBrowserRouter([
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
          { path: 'hire/thread/:threadId', element: <ChatPage /> },
          { path: 'hire/new/:agentId', element: <NewChatPage mode="new" /> },
          { path: 'hire/:agentId', element: <NewChatPage /> },
          { path: 'visit/:chatId', element: <ChatConversationPage /> },
        ],
      },
      {
        path: 'contacts',
        element: <ContactsLayout />,
        children: [
          { index: true, element: <AgentsPage /> },
          { path: 'agents', element: <AgentsPage /> },
          { path: 'agents/:id', element: <AgentDetailPage /> },
          { path: 'users', element: null },
          { path: 'users/:userId', element: <ContactDetailPage /> },
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
