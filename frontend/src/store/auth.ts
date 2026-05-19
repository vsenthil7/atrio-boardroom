import { create } from "zustand";
import { persist } from "zustand/middleware";
import { setAccessToken } from "@/api/client";
import type { User } from "@/types";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  setTokens: (access: string, refresh: string) => void;
  setUser: (u: User | null) => void;
  signOut: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      setTokens: (access, refresh) => {
        setAccessToken(access);
        set({ accessToken: access, refreshToken: refresh });
      },
      setUser: (u) => set({ user: u }),
      signOut: () => {
        setAccessToken(null);
        set({ accessToken: null, refreshToken: null, user: null });
      },
    }),
    {
      name: "atrio-auth",
      onRehydrateStorage: () => (state) => {
        if (state?.accessToken) setAccessToken(state.accessToken);
      },
    },
  ),
);
