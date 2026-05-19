import { apiClient } from "./client";
import type { Document } from "@/types";

export async function uploadDocument(
  sessionId: string,
  file: File,
): Promise<Document> {
  const form = new FormData();
  form.append("file", file);
  const r = await apiClient.post<Document>(
    `/sessions/${sessionId}/documents`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return r.data;
}

export async function listDocuments(sessionId: string): Promise<Document[]> {
  const r = await apiClient.get<Document[]>(`/sessions/${sessionId}/documents`);
  return r.data;
}
