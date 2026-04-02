import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Zap, Users, RefreshCw } from "lucide-react";
import { useAppStore } from "@/store/app-store";
import type { ResourceItem } from "@/store/types";

export default function LibraryItemDetailPage() {
  const { type, id } = useParams<{ type: string; id: string }>();
  const navigate = useNavigate();
  const librarySkills = useAppStore((s) => s.librarySkills);
  const libraryAgents = useAppStore((s) => s.libraryAgents);
  const fetchLibrary = useAppStore((s) => s.fetchLibrary);
  const fetchResourceContent = useAppStore((s) => s.fetchResourceContent);

  const [item, setItem] = useState<ResourceItem | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!type || !id) return;
    fetchLibrary(type === "skill" ? "skill" : "agent");
  }, [type, id, fetchLibrary]);

  useEffect(() => {
    if (!type || !id) return;
    const list = type === "skill" ? librarySkills : libraryAgents;
    const found = list.find((i) => i.id === id);
    if (found) setItem(found);
  }, [librarySkills, libraryAgents, type, id]);

  useEffect(() => {
    if (!type || !id) return;
    setLoading(true);
    fetchResourceContent(type, id)
      .then(setContent)
      .finally(() => setLoading(false));
  }, [type, id, fetchResourceContent]);

  const isSkill = type === "skill";
  const filename = isSkill ? "SKILL.md" : "agent.md";

  if (!item && !loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-sm text-muted-foreground">未找到该内容</span>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto py-6 px-4 md:px-6">
        {/* Back */}
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors duration-fast mb-6"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          返回
        </button>

        {/* Header */}
        <div className="flex items-start gap-4 mb-6">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 bg-warning/10">
                {isSkill
                  ? <Zap className="w-4 h-4 text-warning" />
                  : <Users className="w-4 h-4 text-info" />}
              </div>
              <h1 className="text-xl font-semibold text-foreground">{item?.name ?? id}</h1>
              <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">
                {type}
              </span>
            </div>
            {item?.desc && (
              <p className="text-sm text-muted-foreground mt-2">{item.desc}</p>
            )}
          </div>
        </div>

        {/* File content */}
        <div className="surface-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-mono text-muted-foreground px-2 py-0.5 rounded bg-muted">
              {filename}
            </span>
          </div>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
          ) : content ? (
            <pre className="text-xs text-foreground whitespace-pre-wrap font-mono leading-relaxed max-h-[600px] overflow-y-auto">
              {content}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-6">暂无内容</p>
          )}
        </div>
      </div>
    </div>
  );
}
