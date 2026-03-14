import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, MessageSquare, Search } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";
import { createMemberConversation, listDirectory, type DirectoryEntry, type DirectoryResult } from "@/api/conversations";
import MemberAvatar from "@/components/MemberAvatar";
import { useAuthStore } from "@/store/auth-store";

interface NewChatDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConversationCreated?: () => Promise<void>;
}

// @@@member-directory-dialog - search bar + contacts/others split, shows ALL member types
export default function NewChatDialog({ open, onOpenChange, onConversationCreated }: NewChatDialogProps) {
  const navigate = useNavigate();
  const currentMemberId = useAuthStore(s => s.member?.id);
  const [result, setResult] = useState<DirectoryResult>({ contacts: [], others: [] });
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const fetchDirectory = useCallback((query: string) => {
    setLoading(true);
    // @@@no-type-filter - show all member types, not just agents
    listDirectory(undefined, query || undefined)
      .then((r) => setResult(r))
      .catch((err) => console.error("[NewChatDialog] Failed to fetch directory:", err))
      .finally(() => setLoading(false));
  }, []);

  // Fetch on open
  useEffect(() => {
    if (!open) {
      setSearch("");
      return;
    }
    fetchDirectory("");
  }, [open, fetchDirectory]);

  // Debounced search
  useEffect(() => {
    if (!open) return;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchDirectory(search), 300);
    return () => clearTimeout(debounceRef.current);
  }, [search, open, fetchDirectory]);

  const handleSelect = async (memberId: string) => {
    if (creating) return;
    setCreating(memberId);
    try {
      const conv = await createMemberConversation(memberId);
      onOpenChange(false);
      await onConversationCreated?.();
      // Navigate using the other member's name for URL
      const otherMember = conv.member_details?.find(m => m.id !== currentMemberId);
      const displayName = otherMember?.name || "Chat";
      navigate(`/chat/${displayName}/${conv.id}`);
    } catch (err) {
      console.error("[NewChatDialog] Failed to create conversation:", err);
    } finally {
      setCreating(null);
    }
  };

  const renderEntry = (entry: DirectoryEntry) => {
    const isAgent = entry.type !== "human";
    const ownerName = entry.owner?.name ?? "unknown";
    const subtitle = isAgent ? `${ownerName}'s agent` : "Human";
    const isCreating = creating === entry.id;
    return (
      <button
        key={entry.id}
        onClick={() => void handleSelect(entry.id)}
        disabled={creating !== null}
        className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-muted transition-colors disabled:opacity-50"
      >
        {isCreating ? (
          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
            <Loader2 className="w-4 h-4 animate-spin text-primary" />
          </div>
        ) : (
          <MemberAvatar memberId={entry.id} name={entry.name} size="sm" />
        )}
        <div className="min-w-0 flex-1">
          <span className="text-sm font-medium truncate">{entry.name}</span>
          <p className="text-xs text-muted-foreground truncate mt-0.5">{subtitle}</p>
        </div>
        <MessageSquare className="h-4 w-4 text-muted-foreground shrink-0" />
      </button>
    );
  };

  const hasContacts = result.contacts.length > 0;
  const hasOthers = result.others.length > 0;
  const isEmpty = !hasContacts && !hasOthers && !loading;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md p-0 gap-0">
        <DialogHeader className="px-4 pt-4 pb-3">
          <DialogTitle className="text-base">New Chat</DialogTitle>
          <DialogDescription className="sr-only">Search and select a member to start a conversation</DialogDescription>
        </DialogHeader>

        <div className="px-4 pb-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search members..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm rounded-md border bg-background focus:outline-none focus:ring-1 focus:ring-ring"
              autoFocus
            />
          </div>
        </div>

        <div className="border-t max-h-80 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : isEmpty ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              {search ? "No members found" : "No other members yet"}
            </p>
          ) : (
            <>
              {hasContacts && (
                <div>
                  <div className="px-4 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Contacts
                  </div>
                  {result.contacts.map(renderEntry)}
                </div>
              )}
              {hasOthers && (
                <div>
                  <div className="px-4 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Discover
                  </div>
                  {result.others.map(renderEntry)}
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
