export type EvaluationArtifactRecord = {
  name?: string | null;
  kind?: string | null;
  content?: string | null;
  path?: string | null;
  mime_type?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type ThreadTrajectoryPayload = {
  run_id?: string | null;
  conversation?: Array<Record<string, unknown>> | null;
  events?: Array<{
    seq?: number | null;
    run_id?: string | null;
    event_type?: string | null;
    actor?: string | null;
    summary?: string | null;
    payload?: Record<string, unknown> | null;
  }> | null;
};

export type DownloadArtifactPayload = {
  filename: string;
  mimeType: string;
  text: string;
};

function sanitizeFilePart(value: string | null | undefined, fallback: string): string {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (!normalized) return fallback;
  const safe = normalized.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/-+/g, "-");
  return safe.replace(/^-|-$/g, "") || fallback;
}

export function buildArtifactDownloadPayload(
  runId: string,
  artifact: EvaluationArtifactRecord,
): DownloadArtifactPayload {
  const baseName = sanitizeFilePart(artifact.name || artifact.path, "artifact");
  if (artifact.content) {
    return {
      filename: `${sanitizeFilePart(runId, "run")}-${baseName}.txt`,
      mimeType: artifact.mime_type || "text/plain",
      text: artifact.content,
    };
  }

  return {
    filename: `${sanitizeFilePart(runId, "run")}-${baseName}.json`,
    mimeType: "application/json",
    text: JSON.stringify(artifact, null, 2),
  };
}

export function summarizeTrajectory(trajectory: ThreadTrajectoryPayload | null | undefined) {
  return {
    messageCount: Array.isArray(trajectory?.conversation) ? trajectory?.conversation.length : 0,
    eventCount: Array.isArray(trajectory?.events) ? trajectory?.events.length : 0,
    hasTrace: Boolean(
      (Array.isArray(trajectory?.conversation) && trajectory.conversation.length > 0) ||
        (Array.isArray(trajectory?.events) && trajectory.events.length > 0),
    ),
  };
}
