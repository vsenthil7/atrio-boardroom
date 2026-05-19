import { apiClient } from "./client";
import type { AuditEvent, LiveKitJoin, Mandate } from "@/types";

export async function listAuditForSession(sessionId: string): Promise<AuditEvent[]> {
  const r = await apiClient.get<AuditEvent[]>(`/audit/sessions/${sessionId}`);
  return r.data;
}

export async function listAuditForTenant(params?: {
  since?: string;
  until?: string;
  kind?: string;
}): Promise<AuditEvent[]> {
  const r = await apiClient.get<AuditEvent[]>("/audit/tenant", { params });
  return r.data;
}

export function auditExportUrl(): string {
  return "/api/v1/audit/export";
}

export async function joinVoice(sessionId: string): Promise<LiveKitJoin> {
  const r = await apiClient.post<LiveKitJoin>(`/voice/sessions/${sessionId}/join`);
  return r.data;
}

export async function getActiveMandate(): Promise<Mandate> {
  const r = await apiClient.get<Mandate>("/mandates/active");
  return r.data;
}

export async function listMandates(): Promise<Mandate[]> {
  const r = await apiClient.get<Mandate[]>("/mandates");
  return r.data;
}
