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
      current_instance_id: "runtime-1",
    });

    expect(shell.sandboxLabel).toBe("Sandbox");
    expect(shell.sandboxHref).toBe("/sandboxes/sandbox-1");
  });

  it("uses sandbox ids for provider relations", () => {
    const shell = buildProviderRelationShell({
      provider: { id: "daytona", name: "daytona" },
      sandbox_ids: ["sandbox-1", "sandbox-2"],
      runtime_session_ids: ["runtime-1"],
    });

    expect(shell.sandboxTitle).toBe("Sandboxes");
    expect(shell.sandboxHrefs).toEqual(["/sandboxes/sandbox-1", "/sandboxes/sandbox-2"]);
  });

  it("uses sandbox detail link for runtime relations", () => {
    const shell = buildRuntimeRelationShell({
      provider: { id: "daytona" },
      runtime: { runtimeSessionId: "runtime-1" },
      sandbox_id: "sandbox-1",
      thread_id: "thread-1",
    });

    expect(shell.sandboxLabel).toBe("Sandbox");
    expect(shell.sandboxHref).toBe("/sandboxes/sandbox-1");
  });

  it("uses sandbox operation targets for cleanup relation shells", () => {
    const shell = buildOperationDetailShell({
      operation: { operation_id: "op-1", kind: "sandbox_cleanup", status: "succeeded" },
      target: { target_type: "sandbox", target_id: "sandbox-1" },
      sandbox_id: "sandbox-1",
      result_truth: { sandbox_state_before: "running", sandbox_state_after: "destroyed" },
      events: [],
    });

    expect(shell.surfaceHref).toBe("/sandboxes");
    expect(shell.targetHref).toBe("/sandboxes/sandbox-1");
    expect(shell.targetLabel).toBe("Sandbox");
    expect(shell.beforeLabel).toBe("Sandbox Before");
    expect(shell.afterLabel).toBe("Sandbox After");
    expect(shell.runtimeBody).toBe("Runtime session linked to the target sandbox.");
    expect(shell.providerBody).toBe("Provider surface responsible for the target sandbox runtime.");
  });

  it("uses provider orphan runtime target ids for operation runtime links", () => {
    const shell = buildOperationDetailShell({
      operation: { operation_id: "op-1", status: "succeeded" },
      target: { target_type: "provider_orphan_runtime", provider_id: "daytona", runtime_id: "runtime-1" },
      result_truth: {},
      events: [],
    });

    expect(shell.runtimeHref).toBe("/runtimes/runtime-1");
    expect(shell.runtimeLabel).toBe("runtime-1");
  });

  it("uses sandbox detail link for resource group relation shell", () => {
    expect(buildSandboxGroupDetailLink({ sandboxId: "sandbox-1" })).toEqual({
      href: "/sandboxes/sandbox-1",
      label: "sandbox-1",
    });
  });
});
