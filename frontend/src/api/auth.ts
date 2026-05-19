import { apiClient } from "./client";
import type { TokenResponse, User } from "@/types";

export interface MagicLinkResponse {
  status: string;
  dev_token?: string;
}

export async function requestMagicLink(email: string): Promise<MagicLinkResponse> {
  const r = await apiClient.post<MagicLinkResponse>("/auth/magic-link", { email });
  return r.data;
}

export async function consumeMagicLink(token: string): Promise<TokenResponse> {
  const r = await apiClient.post<TokenResponse>("/auth/magic-link/consume", { token });
  return r.data;
}

export async function refresh(refreshToken: string): Promise<TokenResponse> {
  const r = await apiClient.post<TokenResponse>("/auth/refresh", {
    refresh_token: refreshToken,
  });
  return r.data;
}

export async function me(): Promise<User> {
  const r = await apiClient.get<User>("/auth/me");
  return r.data;
}
