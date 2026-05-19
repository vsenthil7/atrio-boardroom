import { describe, expect, it, beforeEach } from "vitest";
import { useAuthStore } from "@/store/auth";

describe("useAuthStore", () => {
  beforeEach(() => {
    useAuthStore.getState().signOut();
  });

  it("starts signed-out", () => {
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("setTokens stores both tokens", () => {
    useAuthStore.getState().setTokens("a", "r");
    expect(useAuthStore.getState().accessToken).toBe("a");
    expect(useAuthStore.getState().refreshToken).toBe("r");
  });

  it("signOut clears everything", () => {
    useAuthStore.getState().setTokens("a", "r");
    useAuthStore.getState().setUser({
      id: "u",
      email: "x@y.com",
      display_name: "X",
      role: "founder",
      tenant_id: "t",
    });
    useAuthStore.getState().signOut();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().refreshToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });
});
