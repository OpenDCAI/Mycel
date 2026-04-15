import { describe, expect, it } from "vitest";

import { buildOperationDetailShell } from "./OperationDetailPage";
import { buildProviderRelationShell } from "./ProviderDetailPage";
import { buildRuntimeRelationShell } from "./RuntimeDetailPage";
import { buildThreadRelationShell } from "./ThreadDetailPage";
import { buildSandboxGroupDetailLink } from "../ResourcesPage";

describe("monitor relation shell", () => {
  it("uses sandbox detail links for thread relations", () => {
    const shell = buildThreadRelationShell({
      provider_name: "daytona",
      sandbox_id: "sandbox-1",
      lease_id: "lease-1",
      current_instance_id: "runtime-1",
    });

    expect(shell.sandboxLabel).toBe("Sandbox");
    expect(shell.sandboxHref).toBe("/sandboxes/sandbox-1");
  });

  it("uses sandbox ids for provider relations", () => {
    const shell = buildProviderRelationShell({
      provider: { id: "daytona", name: "daytona" },
      sandbox_ids: ["sandbox-1", "sandbox-2"],
      lease_ids: ["lease-1", "lease-2"],
      thread_ids: ["thread-1"],
      runtime_session_ids: ["runtime-1"],
    });

    expect(shell.sandboxTitle).toBe("Sandboxes");
    expect(shell.sandboxHrefs).toEqual(["/sandboxes/sandbox-1", "/sandboxes/sandbox-2"]);
  });

  it("uses sandbox detail link for runtime relations", () => {
    const shell = buildRuntimeRelationShell({
      provider: { id: "daytona" },
      runtime: { runtimeSessionId: "runtime-1", leaseId: "lease-1" },
      sandbox_id: "sandbox-1",
      lease_id: "lease-1",
      thread_id: "thread-1",
    });

    expect(shell.sandboxLabel).toBe("Sandbox");
    expect(shell.sandboxHref).toBe("/sandboxes/sandbox-1");
  });

  it("keeps operation target contract lease-shaped while switching read shell to sandbox", () => {
    const shell = buildOperationDetailShell({
      operation: { operation_id: "op-1", status: "succeeded" },
      target: { target_type: "lease", target_id: "lease-1" },
      sandbox_id: "sandbox-1",
      result_truth: { lease_state_before: "running", lease_state_after: "destroyed" },
      events: [],
    });

    expect(shell.surfaceHref).toBe("/sandboxes");
    expect(shell.targetHref).toBe("/sandboxes/sandbox-1");
    expect(shell.targetLabel).toBe("Sandbox");
    expect(shell.beforeLabel).toBe("Sandbox Before");
    expect(shell.afterLabel).toBe("Sandbox After");
  });

  it("uses sandbox detail link for resource group relation shell", () => {
    expect(buildSandboxGroupDetailLink({ sandboxId: "sandbox-1", leaseId: "lease-1" })).toEqual({
      href: "/sandboxes/sandbox-1",
      label: "sandbox-1",
    });
  });
});
