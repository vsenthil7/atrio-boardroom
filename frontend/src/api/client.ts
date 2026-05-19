import axios, { AxiosError, type AxiosInstance } from "axios";
import type { ApiError } from "@/types";

const BASE_URL = "/api/v1";

let _accessToken: string | null = null;
let _onUnauthorised: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  _accessToken = token;
}

export function onUnauthorised(fn: () => void): void {
  _onUnauthorised = fn;
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config) => {
  if (_accessToken) {
    config.headers.set("Authorization", `Bearer ${_accessToken}`);
  }
  return config;
});

apiClient.interceptors.response.use(
  (r) => r,
  (err: AxiosError<ApiError>) => {
    if (err.response?.status === 401 && _onUnauthorised) {
      _onUnauthorised();
    }
    return Promise.reject(err);
  },
);

export function apiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const e = err.response?.data as ApiError | undefined;
    if (e?.error?.message) return e.error.message;
    if (err.message) return err.message;
  }
  if (err instanceof Error) return err.message;
  return "Unexpected error";
}
