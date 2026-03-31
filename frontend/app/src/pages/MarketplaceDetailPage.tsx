import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Download, Clock, Tag, User, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useMarketplaceStore } from "@/store/marketplace-store";
import LineageTree from "@/components/marketplace/LineageTree";
import InstallDialog from "@/components/marketplace/InstallDialog";

const typeBadgeColors: Record<string, string> = {
  member: "bg-blue-500/10 text-blue-600",
  agent: "bg-purple-500/10 text-purple-600",
  skill: "bg-amber-500/10 text-amber-600",
  env: "bg-green-500/10 text-green-600",
};

export default function MarketplaceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const detail = useMarketplaceStore((s) => s.detail);
  const detailLoading = useMarketplaceStore((s) => s.detailLoading);
  const fetchDetail = useMarketplaceStore((s) => s.fetchDetail);
  const lineage = useMarketplaceStore((s) => s.lineage);
  const fetchLineage = useMarketplaceStore((s) => s.fetchLineage);
  const clearDetail = useMarketplaceStore((s) => s.clearDetail);
  const [installOpen, setInstallOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "versions">("overview");

  useEffect(() => {
    if (id) {
      fetchDetail(id);
      fetchLineage(id);
    }
    return () => clearDetail();
  }, [id, fetchDetail, fetchLineage, clearDetail]);

  if (detailLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        Item not found
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto py-6 px-4 md:px-6">
        {/* Back button */}
        <button
          onClick={() => navigate("/marketplace")}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mb-6"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Marketplace
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
            Download
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

        {/* Tabs */}
        <div className="flex gap-4 border-b border-border mb-6">
          {(["overview", "versions"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-2 text-sm font-medium capitalize transition-colors border-b-2 ${
                activeTab === tab ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* Lineage */}
            <LineageTree
              ancestors={lineage.ancestors}
              children={lineage.children}
              currentName={detail.name}
              onNodeClick={(nodeId) => navigate(`/marketplace/${nodeId}`)}
            />

            {/* Latest version info */}
            {detail.versions.length > 0 && (
              <div className="surface-card p-4 space-y-2">
                <h3 className="text-sm font-medium text-foreground">Latest Version</h3>
                <p className="text-xs font-mono text-primary">v{detail.versions[0].version}</p>
                {detail.versions[0].release_notes && (
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">{detail.versions[0].release_notes}</p>
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === "versions" && (
          <div className="space-y-3">
            {detail.versions.map((v) => (
              <div key={v.id} className="surface-card p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-mono font-medium text-foreground">v{v.version}</span>
                  <span className="text-[11px] text-muted-foreground">{new Date(v.created_at).toLocaleDateString()}</span>
                </div>
                {v.release_notes && (
                  <p className="text-xs text-muted-foreground whitespace-pre-wrap">{v.release_notes}</p>
                )}
              </div>
            ))}
            {detail.versions.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-8">No versions published yet</p>
            )}
          </div>
        )}
      </div>

      {/* Install dialog */}
      <InstallDialog open={installOpen} onOpenChange={setInstallOpen} item={detail} />
    </div>
  );
}
