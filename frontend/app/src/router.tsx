import { createBrowserRouter, Navigate, useParams } from 'react-router-dom';
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
import ThreadsIndexRedirect from './pages/ThreadsIndexRedirect';

/** Redirect legacy /threads paths onto the split template-entry/runtime hire routes. */
function ThreadsLegacyRedirect() {
  const params = useParams();
  const rest = params['*'] || '';
  const parts = rest.split('/').filter(Boolean);
  if (parts.length >= 2) {
    return <Navigate to={`/chat/hire/thread/${encodeURIComponent(parts[parts.length - 1]!)}`} replace />;
  }
  if (parts.length === 1) {
    return <Navigate to={`/chat/hire/${encodeURIComponent(parts[0]!)}`} replace />;
  }
  return <Navigate to="/chat" replace />;
}

/** Redirect /chat/hire/:memberId/:threadId → /chat/hire/thread/:threadId */
function HireThreadLegacyRedirect() {
  const { threadId } = useParams<{ memberId: string; threadId: string }>();
  if (!threadId) return <Navigate to="/chat" replace />;
  return <Navigate to={`/chat/hire/thread/${encodeURIComponent(threadId)}`} replace />;
}

export const router = createBrowserRouter([
  // Legacy redirects — preserve path segments
  { path: '/threads', element: <ThreadsIndexRedirect /> },
  { path: '/threads/*', element: <ThreadsLegacyRedirect /> },
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
          { path: 'hire/thread/:threadId', element: <ChatPage /> },
          { path: 'hire/:memberId/:threadId', element: <HireThreadLegacyRedirect /> },
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
