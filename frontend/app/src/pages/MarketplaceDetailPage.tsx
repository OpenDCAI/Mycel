import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Download, Clock, Tag, User, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useMarketplaceStore } from "@/store/marketplace-store";
import LineageTree from "@/components/marketplace/LineageTree";
import InstallDialog from "@/components/marketplace/InstallDialog";
import { typeBadgeColors } from "@/components/marketplace/constants";

export default function MarketplaceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const detail = useMarketplaceStore((s) => s.detail);
  const detailLoading = useMarketplaceStore((s) => s.detailLoading);
  const fetchDetail = useMarketplaceStore((s) => s.fetchDetail);
  const lineage = useMarketplaceStore((s) => s.lineage);
  const fetchLineage = useMarketplaceStore((s) => s.fetchLineage);
  const clearDetail = useMarketplaceStore((s) => s.clearDetail);
  const error = useMarketplaceStore((s) => s.error);
  const versionSnapshot = useMarketplaceStore((s) => s.versionSnapshot);
  const snapshotLoading = useMarketplaceStore((s) => s.snapshotLoading);
  const fetchVersionSnapshot = useMarketplaceStore((s) => s.fetchVersionSnapshot);
  const clearSnapshot = useMarketplaceStore((s) => s.clearSnapshot);
  const [installOpen, setInstallOpen] = useState(false);
  const detailId = detail?.id;
  const detailType = detail?.type;
  const previewVersion = detail?.versions[0]?.version;

  useEffect(() => {
    if (id) {
      fetchDetail(id);
      fetchLineage(id);
    }
    return () => clearDetail();
  }, [id, fetchDetail, fetchLineage, clearDetail]);

  useEffect(() => {
    if (detailId && previewVersion && (detailType === "skill" || detailType === "agent")) {
      fetchVersionSnapshot(detailId, previewVersion);
    }
    return () => clearSnapshot();
  }, [detailId, detailType, previewVersion, fetchVersionSnapshot, clearSnapshot]);

  if (detailLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        {error ? (
          <div className="flex items-center justify-between px-4 py-2.5 rounded-lg bg-destructive/10 text-destructive text-sm max-w-md w-full">
            <span>{error}</span>
            <button onClick={() => id && fetchDetail(id)} className="text-xs underline">重试</button>
          </div>
        ) : (
          <span className="text-sm text-muted-foreground">未找到该内容</span>
        )}
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto py-6 px-4 md:px-6">
        {/* Back button */}
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
              <h1 className="text-xl font-semibold text-foreground">{detail.name}</h1>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${typeBadgeColors[detail.type] || "bg-muted text-muted-foreground"}`}>
                {detail.type}
              </span>
            </div>
            <p className="text-sm text-muted-foreground mb-3">{detail.description || "No description"}</p>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1"><User className="w-3 h-3" />{detail.publisher_username}</span>
              <span className="flex items-center gap-1"><Download className="w-3 h-3" />{detail.download_count} downloads</span>
              <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(detail.created_at).toLocaleDateString()}</span>
            </div>
          </div>
          <Button onClick={() => setInstallOpen(true)} className="shrink-0">
            <Download className="w-4 h-4 mr-2" />
            下载
          </Button>
        </div>

        {/* Tags */}
        {detail.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-6">
            {detail.tags.map((tag) => (
              <span key={tag} className="flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-muted text-muted-foreground">
                <Tag className="w-3 h-3" />{tag}
              </span>
            ))}
          </div>
        )}

        <div className="space-y-6">
          {/* Lineage */}
          <LineageTree
            ancestors={lineage.ancestors}
            children={lineage.children}
            currentName={detail.name}
            onNodeClick={(nodeId) => navigate(`/marketplace/${nodeId}`)}
          />

          {/* Version history */}
          {detail.versions.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-medium text-foreground">版本历史</h3>
              {detail.versions.map((v) => (
                <div key={v.id} className="surface-card p-4">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-mono font-medium text-primary">v{v.version}</span>
                    <span className="text-2xs text-muted-foreground">{new Date(v.created_at).toLocaleDateString()}</span>
                  </div>
                  {v.release_notes && (
                    <p className="text-xs text-muted-foreground whitespace-pre-wrap">{v.release_notes}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* File content for skill / agent */}
          {(detail.type === "skill" || detail.type === "agent") && (
            <div className="surface-card p-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-mono text-muted-foreground px-2 py-0.5 rounded bg-muted">
                  {detail.type === "skill" ? "SKILL.md" : "agent.md"}
                </span>
              </div>
              {snapshotLoading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="w-4 h-4 animate-spin text-muted-foreground" />
                </div>
              ) : versionSnapshot?.content ? (
                <pre className="text-xs text-foreground whitespace-pre-wrap font-mono leading-relaxed max-h-[500px] overflow-y-auto">
                  {versionSnapshot.content}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-6">暂无内容</p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Install dialog */}
      <InstallDialog open={installOpen} onOpenChange={setInstallOpen} item={detail} />
    </div>
  );
}
