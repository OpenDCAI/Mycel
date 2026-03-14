import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import ForceGraph from "react-force-graph-2d";
import type { ForceGraphMethods } from "react-force-graph-2d";
import { fetchGraph, type GraphNode, type GraphEdge } from "../api/network";
import { useAuthStore } from "../store/auth-store";

interface FGNode extends GraphNode {
  x?: number;
  y?: number;
}

interface FGLink {
  source: string | FGNode;
  target: string | FGNode;
  weight: number;
}

type ViewMode = "global" | "ego";

// @@@breathing-glow — animate glow radius for the user's own agent node
const GLOW_PERIOD = 2000;
function glowRadius(t: number): number {
  const phase = (t % GLOW_PERIOD) / GLOW_PERIOD;
  return 12 + 6 * Math.sin(phase * Math.PI * 2);
}

function hexagonPath(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 2;
    const px = x + r * Math.cos(angle);
    const py = y + r * Math.sin(angle);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
}

const NODE_R = 6;
const COLORS: Record<string, string> = {
  human: "#60a5fa",
  mycel_agent: "#4ade80",
  openclaw_agent: "#fb923c",
};

// @@@ego-bfs — compute visible node set from center node within depth hops
function bfs(
  centerId: string,
  depth: number,
  edges: { source: string; target: string; weight: number }[],
  minWeight: number,
): Set<string> {
  const adj = new Map<string, string[]>();
  for (const e of edges) {
    if (e.weight < minWeight) continue;
    if (!adj.has(e.source)) adj.set(e.source, []);
    if (!adj.has(e.target)) adj.set(e.target, []);
    adj.get(e.source)!.push(e.target);
    adj.get(e.target)!.push(e.source);
  }
  const visited = new Set<string>();
  let frontier = [centerId];
  visited.add(centerId);
  for (let d = 0; d < depth; d++) {
    const next: string[] = [];
    for (const nid of frontier) {
      for (const nb of adj.get(nid) ?? []) {
        if (!visited.has(nb)) {
          visited.add(nb);
          next.push(nb);
        }
      }
    }
    frontier = next;
  }
  return visited;
}

// ---------------------------------------------------------------------------
// Minimap component — renders a small overview in bottom-right
// ---------------------------------------------------------------------------
const MINIMAP_W = 160;
const MINIMAP_H = 120;

function Minimap({ nodes, links }: { nodes: FGNode[]; links: FGLink[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext("2d");
    if (!ctx) return;

    let raf: number;
    const draw = () => {
      ctx.clearRect(0, 0, MINIMAP_W, MINIMAP_H);

      // Compute bounds
      const xs = nodes.map((n) => n.x ?? 0);
      const ys = nodes.map((n) => n.y ?? 0);
      if (xs.length === 0) return;
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const rangeX = maxX - minX || 1;
      const rangeY = maxY - minY || 1;
      const pad = 12;
      const scaleX = (MINIMAP_W - pad * 2) / rangeX;
      const scaleY = (MINIMAP_H - pad * 2) / rangeY;
      const scale = Math.min(scaleX, scaleY);
      const offX = pad + ((MINIMAP_W - pad * 2) - rangeX * scale) / 2;
      const offY = pad + ((MINIMAP_H - pad * 2) - rangeY * scale) / 2;
      const tx = (n: FGNode) => offX + ((n.x ?? 0) - minX) * scale;
      const ty = (n: FGNode) => offY + ((n.y ?? 0) - minY) * scale;

      // Links
      ctx.strokeStyle = "rgba(148,163,184,0.25)";
      ctx.lineWidth = 0.5;
      for (const link of links) {
        const s = typeof link.source === "string" ? null : link.source;
        const t = typeof link.target === "string" ? null : link.target;
        if (!s || !t) continue;
        ctx.beginPath();
        ctx.moveTo(tx(s), ty(s));
        ctx.lineTo(tx(t), ty(t));
        ctx.stroke();
      }

      // Nodes
      for (const n of nodes) {
        ctx.fillStyle = COLORS[n.type] || "#a78bfa";
        ctx.beginPath();
        ctx.arc(tx(n), ty(n), 2.5, 0, 2 * Math.PI);
        ctx.fill();
      }

      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [nodes, links]);

  return (
    <canvas
      ref={canvasRef}
      width={MINIMAP_W}
      height={MINIMAP_H}
      className="absolute bottom-3 right-3 rounded-lg border border-border bg-card/80 backdrop-blur-sm"
      style={{ pointerEvents: "none" }}
    />
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
export default function NetworkPage() {
  // --- raw data ---
  const [allNodes, setAllNodes] = useState<FGNode[]>([]);
  const [allEdges, setAllEdges] = useState<{ source: string; target: string; weight: number }[]>([]);
  const [error, setError] = useState<string | null>(null);

  // --- controls ---
  const [mode, setMode] = useState<ViewMode>("global");
  const [centerId, setCenterId] = useState<string | null>(null);
  const [depth, setDepth] = useState(2);
  const [minWeight, setMinWeight] = useState(1);
  const [agentsOnly, setAgentsOnly] = useState(false);

  // --- layout ---
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<ForceGraphMethods<FGNode, FGLink>>();
  const myAgentId = useAuthStore((s) => s.agent?.id);
  const myMemberId = useAuthStore((s) => s.member?.id);

  // --- label color from theme ---
  const [labelColor, setLabelColor] = useState("#334155");
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const fg = getComputedStyle(el).getPropertyValue("color");
    if (fg) setLabelColor(fg);
  }, []);

  // @@@avatar-canvas-cache — pre-load avatar images for Canvas drawImage
  const avatarCache = useRef<Map<string, HTMLImageElement | null>>(new Map());
  const [avatarLoadCount, setAvatarLoadCount] = useState(0); // trigger re-render on load

  // --- fetch ---
  useEffect(() => {
    fetchGraph()
      .then((data) => {
        setAllNodes(data.nodes);
        setAllEdges(data.edges);
        setCenterId(myAgentId ?? myMemberId ?? data.nodes[0]?.id ?? null);

        // Pre-load avatar images for all nodes
        avatarCache.current.clear();
        for (const node of data.nodes) {
          const img = new Image();
          img.onload = () => {
            avatarCache.current.set(node.id, img);
            setAvatarLoadCount((c) => c + 1);
          };
          img.onerror = () => {
            avatarCache.current.set(node.id, null); // no avatar
          };
          img.src = `/api/members/${node.id}/avatar`;
        }
      })
      .catch((err) => setError(err.message));
  }, [myAgentId, myMemberId]);

  // --- max weight for slider ---
  const maxWeight = useMemo(
    () => Math.max(1, ...allEdges.map((e) => e.weight)),
    [allEdges],
  );

  // --- node type lookup for agents-only filter ---
  const nodeTypeMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const n of allNodes) m.set(n.id, n.type);
    return m;
  }, [allNodes]);

  // --- filtered graph data ---
  const graphData = useMemo(() => {
    if (allNodes.length === 0) return null;

    // Pre-filter edges by agents-only + weight
    const filteredEdges = allEdges.filter((e) => {
      if (e.weight < minWeight) return false;
      if (agentsOnly) {
        return nodeTypeMap.get(e.source) !== "human" && nodeTypeMap.get(e.target) !== "human";
      }
      return true;
    });

    let visibleNodeIds: Set<string>;
    if (mode === "ego" && centerId) {
      visibleNodeIds = bfs(centerId, depth, filteredEdges, 1); // already weight-filtered
    } else {
      visibleNodeIds = new Set<string>();
      for (const e of filteredEdges) {
        visibleNodeIds.add(e.source);
        visibleNodeIds.add(e.target);
      }
    }

    const nodes = allNodes.filter(
      (n) => visibleNodeIds.has(n.id) && (!agentsOnly || n.type !== "human"),
    );
    const links: FGLink[] = filteredEdges
      .filter((e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target))
      .map((e) => ({ source: e.source, target: e.target, weight: e.weight }));

    return { nodes, links };
  }, [allNodes, allEdges, nodeTypeMap, mode, centerId, depth, minWeight, agentsOnly]);

  // --- zoom to fit after engine settles ---
  const hasZoomed = useRef(false);
  useEffect(() => { hasZoomed.current = false; }, [graphData]);

  // --- configure forces ---
  useEffect(() => {
    if (!fgRef.current) return;
    const fg = fgRef.current;
    const charge = fg.d3Force("charge");
    if (charge && typeof charge.strength === "function") charge.strength(-120);
    const link = fg.d3Force("link");
    if (link && typeof link.distance === "function") link.distance(60);
  }, [graphData]);

  // --- resize ---
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width, height });
    });
    ro.observe(el);
    setDimensions({ width: el.clientWidth, height: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  // --- node paint ---
  const paintNode = useCallback(
    (node: FGNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const r = NODE_R;
      const color = COLORS[node.type] || "#a78bfa";
      const isMyAgent = node.id === myAgentId;
      const isMe = node.id === myMemberId;
      const isCenter = mode === "ego" && node.id === centerId;
      const avatarImg = avatarCache.current.get(node.id);

      // Glow for own agent or self (always behind everything)
      if (isMyAgent || isMe) {
        const gr = glowRadius(performance.now());
        const gradient = ctx.createRadialGradient(x, y, r, x, y, gr);
        gradient.addColorStop(0, color + "80");
        gradient.addColorStop(1, color + "00");
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(x, y, gr, 0, 2 * Math.PI);
        ctx.fill();
      }

      // @@@avatar-canvas-draw — clip to shape, draw avatar or fallback color
      if (avatarImg && globalScale > 0.3) {
        // Draw avatar image clipped to circle (all nodes use circle clip for avatar)
        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, r, 0, 2 * Math.PI);
        ctx.clip();
        ctx.drawImage(avatarImg, x - r, y - r, r * 2, r * 2);
        ctx.restore();
      } else {
        // Fallback: colored shape
        if (node.type === "human") {
          ctx.beginPath();
          ctx.arc(x, y, r, 0, 2 * Math.PI);
        } else {
          hexagonPath(ctx, x, y, r);
        }
        ctx.fillStyle = color;
        ctx.fill();
      }

      // Ring: ego center > self/own-agent > default
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      if (isCenter) {
        ctx.strokeStyle = "#f59e0b";
        ctx.lineWidth = 2;
      } else if (isMyAgent || isMe) {
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 1.5;
      } else if (!avatarImg) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 0.5;
      } else {
        ctx.strokeStyle = "rgba(0,0,0,0.15)";
        ctx.lineWidth = 0.5;
      }
      ctx.stroke();

      // Label
      const fontSize = Math.max(11 / globalScale, 3);
      ctx.font = `${fontSize}px -apple-system, "Segoe UI", Roboto, sans-serif`;
      ctx.letterSpacing = `${0.5 / globalScale}px`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = labelColor;
      ctx.fillText(node.name, x, y + r + 2);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [myAgentId, myMemberId, labelColor, mode, centerId, avatarLoadCount],
  );

  const paintNodeArea = useCallback(
    (node: FGNode, color: string, ctx: CanvasRenderingContext2D) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, NODE_R + 2, 0, 2 * Math.PI);
      ctx.fill();
    },
    [],
  );

  // --- click node → set as ego center ---
  const handleNodeClick = useCallback(
    (node: FGNode) => {
      if (mode === "ego") {
        setCenterId(node.id);
      }
    },
    [mode],
  );

  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <p className="text-destructive text-sm">{error}</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full w-full bg-background relative">
      {/* --- Toolbar --- */}
      <div className="absolute top-3 left-3 z-10 flex items-center gap-2 bg-card/80 backdrop-blur-sm border border-border rounded-lg px-3 py-2 text-xs">
        {/* Mode toggle */}
        <div className="flex rounded-md border border-border overflow-hidden">
          <button
            onClick={() => setMode("global")}
            className={`px-2.5 py-1 transition-colors ${mode === "global" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}
          >
            全局
          </button>
          <button
            onClick={() => setMode("ego")}
            className={`px-2.5 py-1 transition-colors ${mode === "ego" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"}`}
          >
            中心
          </button>
        </div>

        {/* Center node selector — ego mode only */}
        {mode === "ego" && (
          <>
            <select
              value={centerId ?? ""}
              onChange={(e) => setCenterId(e.target.value)}
              className="bg-card border border-border rounded px-2 py-1 text-xs max-w-[140px]"
            >
              {allNodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name}
                </option>
              ))}
            </select>

            <label className="text-muted-foreground ml-1">深度</label>
            <input
              type="range"
              min={1}
              max={5}
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
              className="w-16 accent-primary"
            />
            <span className="text-muted-foreground w-3">{depth}</span>
          </>
        )}

        {/* Weight threshold — both modes */}
        {maxWeight > 1 && (
          <>
            <label className="text-muted-foreground ml-1">强度≥</label>
            <input
              type="range"
              min={1}
              max={maxWeight}
              value={minWeight}
              onChange={(e) => setMinWeight(Number(e.target.value))}
              className="w-16 accent-primary"
            />
            <span className="text-muted-foreground w-3">{minWeight}</span>
          </>
        )}

        {/* Agents-only toggle */}
        <button
          onClick={() => setAgentsOnly(!agentsOnly)}
          className={`ml-1 px-2.5 py-1 rounded-md border transition-colors ${
            agentsOnly
              ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-600"
              : "border-border text-muted-foreground hover:bg-muted"
          }`}
        >
          仅Agent
        </button>
      </div>

      {/* --- Graph --- */}
      {graphData && (
        <ForceGraph
          ref={fgRef}
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="transparent"
          nodeCanvasObject={paintNode}
          nodeCanvasObjectMode={() => "replace"}
          nodePointerAreaPaint={paintNodeArea}
          onNodeClick={handleNodeClick}
          linkColor={() => "rgba(148,163,184,0.3)"}
          linkWidth={(link: FGLink) => Math.max(1, Math.min(8, 1 + (link.weight / Math.max(1, maxWeight)) * 7))}
          linkDirectionalParticles={(link: FGLink) => Math.min(Math.ceil(link.weight / Math.max(1, maxWeight) * 4), 4)}
          linkDirectionalParticleSpeed={0.005}
          linkDirectionalParticleWidth={2}
          linkDirectionalParticleColor={() => "rgba(148,163,184,0.6)"}
          autoPauseRedraw={false}
          cooldownTime={3000}
          enableNodeDrag={true}
          onEngineStop={() => {
            if (!hasZoomed.current && fgRef.current) {
              hasZoomed.current = true;
              fgRef.current.zoomToFit(400, 60);
            }
          }}
        />
      )}

      {/* --- Minimap --- */}
      {graphData && <Minimap nodes={graphData.nodes} links={graphData.links} />}
    </div>
  );
}
