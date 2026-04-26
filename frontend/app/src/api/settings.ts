import { asRecord } from "../lib/records";
import { authFetch } from "../store/auth-store";
import type { AccountResourceLimit } from "./types";

export async function fetchDefaultModel(): Promise<string> {
  const response = await authFetch("/api/settings");
  if (!response.ok) {
    throw new Error(`Settings API ${response.status}: ${await response.text()}`);
  }
  const settings = asRecord(await response.json());
  const defaultModel = settings?.default_model;
  if (typeof defaultModel !== "string" || !defaultModel.trim()) {
    throw new Error("Settings payload missing default_model");
  }
  return defaultModel;
}

function parseAccountResourceLimits(value: unknown): AccountResourceLimit[] {
  const items = asRecord(value)?.items;
  if (!Array.isArray(items)) throw new Error("Malformed account resource limits");
  return items.map((item) => {
    const row = asRecord(item);
    if (
      !row
      || typeof row.resource !== "string"
      || typeof row.provider_name !== "string"
      || typeof row.label !== "string"
      || typeof row.limit !== "number"
      || typeof row.used !== "number"
      || typeof row.remaining !== "number"
      || typeof row.can_create !== "boolean"
    ) {
      throw new Error("Malformed account resource limits");
    }
    return {
      resource: row.resource,
      provider_name: row.provider_name,
      label: row.label,
      limit: row.limit,
      used: row.used,
      remaining: row.remaining,
      can_create: row.can_create,
      period: typeof row.period === "string" ? row.period : undefined,
      unit: typeof row.unit === "string" ? row.unit : undefined,
    };
  });
}

export async function fetchAccountResourceLimits(signal?: AbortSignal): Promise<AccountResourceLimit[]> {
  const response = await authFetch("/api/settings/account-resources", { signal });
  if (!response.ok) {
    throw new Error(`Account resources API ${response.status}: ${await response.text()}`);
  }
  return parseAccountResourceLimits(await response.json());
}
