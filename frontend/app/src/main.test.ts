import { describe, expect, it } from "vitest";

const sourceModules = import.meta.glob("./main.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("app main entry", () => {
  it("does not wrap the app in StrictMode", () => {
    const source = sourceModules["./main.tsx"];

    expect(source).not.toContain("StrictMode");
    expect(source).toContain("<RouterProvider router={router} />");
  });
});
