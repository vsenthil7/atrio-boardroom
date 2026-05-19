import { apiClient } from "./client";
import type { Session, SessionList, TurnList } from "@/types";

export async function listSessions(): Promise<SessionList> {
  const r = await apiClient.get<SessionList>("/sessions");
  return r.data;
}

export async function createSession(input: {
  title?: string;
  language_dominant?: string;
}): Promise<Session> {
  const r = await apiClient.post<Session>("/sessions", input);
  return r.data;
}

export async function getSession(id: string): Promise<Session> {
  const r = await apiClient.get<Session>(`/sessions/${id}`);
  return r.data;
}

export async function listTurns(sessionId: string): Promise<TurnList> {
  const r = await apiClient.get<TurnList>(`/sessions/${sessionId}/turns`);
  return r.data;
}

export async function closeSession(id: string): Promise<Session> {
  const r = await apiClient.post<Session>(`/sessions/${id}/close`);
  return r.data;
}

export function boardpackUrl(sessionId: string): string {
  return `/api/v1/sessions/${sessionId}/boardpack.pdf`;
}
