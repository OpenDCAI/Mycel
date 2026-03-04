import type { AllocatedResource, ProviderInfo, ResourceType } from "./types";
import { CAPABILITY_KEYS } from "./capabilities";

/** Derive allocated resources from provider sessions and enabled capabilities. */
export function deriveAllocatedResources(providers: ProviderInfo[]): AllocatedResource[] {
  const resources: AllocatedResource[] = [];
  for (const provider of providers) {
    for (const session of provider.sessions) {
      if (session.status === "stopped") {
        continue;
      }
      for (const key of CAPABILITY_KEYS) {
        if (provider.capabilities[key]) {
          resources.push({
            resourceType: key as ResourceType,
            providerId: provider.id,
            providerName: provider.name,
            threadId: session.threadId,
            agentId: session.agentId,
            agentName: session.agentName,
            sessionId: session.id,
            sessionStatus: session.status,
          });
        }
      }
    }
  }
  return resources;
}
