import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Zap, Users, RefreshCw } from "lucide-react";
import SandboxTemplateEditor from "@/components/SandboxTemplateEditor";
import { useAppStore } from "@/store/app-store";
import type { ResourceItem } from "@/store/types";

type DetailLibraryType = "skill" | "agent" | "sandbox-template";

function detailLibraryType(value: string | undefined): DetailLibraryType | null {
  return value === "skill" || value === "agent" || value === "sandbox-template" ? value : null;
}

function installedDetailReturnTarget(type: DetailLibraryType | null): string {
  if (type === "skill") return "/marketplace?tab=installed&sub=skill";
  if (type === "agent") return "/marketplace?tab=installed&sub=agent";
  return "/marketplace?tab=installed&sub=sandbox-template";
}

export default function LibraryItemDetailPage() {
  const { type, id } = useParams<{ type: string; id: string }>();
  const navigate = useNavigate();
  const librarySkills = useAppStore((s) => s.librarySkills);
  const libraryAgents = useAppStore((s) => s.libraryAgents);
  const librarySandboxTemplates = useAppStore((s) => s.librarySandboxTemplates);
  const librariesLoaded = useAppStore((s) => s.librariesLoaded);
  const ensureLibrary = useAppStore((s) => s.ensureLibrary);
  const fetchResourceContent = useAppStore((s) => s.fetchResourceContent);
  const libraryType = detailLibraryType(type);

  const contentKey = type && id ? `${type}:${id}` : "";
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [contentState, setContentState] = useState<{ key: string; content: string; error: string | null }>({
    key: "",
    content: "",
    error: null,
  });

  const item = useMemo<ResourceItem | null>(() => {
    if (!type || !id) return null;
    const list = type === "skill" ? librarySkills : type === "agent" ? libraryAgents : type === "sandbox-template" ? librarySandboxTemplates : [];
    return list.find((i) => i.id === id) ?? null;
  }, [librarySkills, libraryAgents, librarySandboxTemplates, type, id]);

  useEffect(() => {
    if (!libraryType || librariesLoaded[libraryType]) return;
    let cancelled = false;
    ensureLibrary(libraryType).catch((err: unknown) => {
      if (!cancelled) {
        setLibraryError(err instanceof Error ? err.message : "加载失败");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [ensureLibrary, librariesLoaded, libraryType]);

  useEffect(() => {
    if (!type || !id || type === "sandbox-template") return;
    const key = `${type}:${id}`;
    let cancelled = false;
    fetchResourceContent(type, id)
      .then((content) => {
        if (!cancelled) {
          setContentState({ key, content, error: null });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setContentState({
            key,
            content: "",
            error: err instanceof Error ? err.message : "加载失败",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [type, id, fetchResourceContent]);

  const isSkill = type === "skill";
  const isSandboxTemplate = type === "sandbox-template";
  const filename = isSkill ? "SKILL.md" : "agent.md";
  const loadingLibrary = !!libraryType && !librariesLoaded[libraryType] && !libraryError;
  const loading = loadingLibrary || (!isSandboxTemplate && !!contentKey && contentState.key !== contentKey);
  const content = contentState.key === contentKey ? contentState.content : "";
  const error = libraryError ?? (contentState.key === contentKey ? contentState.error : null);

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
          onClick={() => navigate(installedDetailReturnTarget(libraryType))}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors duration-fast mb-6"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          返回
        </button>

        {!isSandboxTemplate && (
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
        )}

        {isSandboxTemplate && item ? (
          <SandboxTemplateEditor item={item} onDeleted={() => navigate("/marketplace?tab=installed&sub=sandbox-template")} />
        ) : (
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
          ) : error ? (
            <p className="text-sm text-destructive text-center py-6">{error}</p>
          ) : content ? (
            <pre className="text-xs text-foreground whitespace-pre-wrap font-mono leading-relaxed max-h-[600px] overflow-y-auto">
              {content}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-6">暂无内容</p>
          )}
          </div>
        )}
      </div>
    </div>
  );
}
