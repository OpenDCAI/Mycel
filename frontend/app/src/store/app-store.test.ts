// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";
import { useAppStore } from "./app-store";

describe("useAppStore", () => {
  beforeEach(() => {
    useAppStore.setState({
      memberList: [],
      taskList: [],
      cronJobs: [],
      librarySkills: [],
      libraryMcps: [],
      libraryAgents: [],
      libraryRecipes: [],
      userProfile: { name: "User", initials: "U", email: "" },
      loaded: false,
      error: null,
    });
  });

  it("resets loaded member state when auth identity changes", () => {
    useAppStore.setState({
      memberList: [{ id: "m-old", name: "Old", status: "active" } as never],
      loaded: true,
      error: "stale",
    });

    useAppStore.getState().resetSessionData();

    const state = useAppStore.getState();
    expect(state.memberList).toEqual([]);
    expect(state.loaded).toBe(false);
    expect(state.error).toBeNull();
  });
});
