import { apiClient } from "./client";
import type { TreasuryProposal } from "@/types";

export async function proposeTreasury(input: {
  session_id: string;
  instrument: string;
  side: "buy" | "sell";
  qty: string;
  expected_price?: string;
}): Promise<TreasuryProposal> {
  const r = await apiClient.post<TreasuryProposal>("/treasury/proposals", input);
  return r.data;
}

export async function listProposals(state?: string): Promise<TreasuryProposal[]> {
  const r = await apiClient.get<TreasuryProposal[]>("/treasury/proposals", {
    params: state ? { state } : undefined,
  });
  return r.data;
}

export async function getProposal(id: string): Promise<TreasuryProposal> {
  const r = await apiClient.get<TreasuryProposal>(`/treasury/proposals/${id}`);
  return r.data;
}

export async function authoriseProposal(id: string): Promise<TreasuryProposal> {
  const r = await apiClient.post<TreasuryProposal>(
    `/treasury/proposals/${id}/authorise`,
    { confirm: true },
  );
  return r.data;
}

export async function rejectProposal(id: string, reason: string): Promise<TreasuryProposal> {
  const r = await apiClient.post<TreasuryProposal>(
    `/treasury/proposals/${id}/reject`,
    { reason },
  );
  return r.data;
}
