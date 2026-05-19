import { create } from "zustand";
import type { SSEEvent, Stance, Turn } from "@/types";

export interface StreamingPosition {
  agent_id: string;
  text: string;
  stance: Stance;
  model_used: string;
  was_fallback: boolean;
  latency_ms: number;
  dissent_round: number | null;
}

interface SessionState {
  currentSessionId: string | null;
  turns: Turn[]; // historical turns from API
  positions: StreamingPosition[]; // streaming output for the current turn
  isStreaming: boolean;
  dissentRound: number | null;
  consensus: { text: string; kind: string; action_list: unknown[] } | null;
  setCurrentSession: (id: string | null) => void;
  setTurns: (t: Turn[]) => void;
  beginStream: () => void;
  applyEvent: (e: SSEEvent) => void;
  endStream: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  currentSessionId: null,
  turns: [],
  positions: [],
  isStreaming: false,
  dissentRound: null,
  consensus: null,
  setCurrentSession: (id) =>
    set({
      currentSessionId: id,
      turns: [],
      positions: [],
      isStreaming: false,
      dissentRound: null,
      consensus: null,
    }),
  setTurns: (t) => set({ turns: t }),
  beginStream: () =>
    set({ positions: [], isStreaming: true, dissentRound: null, consensus: null }),
  applyEvent: (e) => {
    switch (e.event) {
      case "agent_done":
        set((s) => ({
          positions: [
            ...s.positions,
            {
              agent_id: e.data.agent_id,
              text: e.data.text,
              stance: e.data.stance,
              model_used: e.data.model_used,
              was_fallback: e.data.was_fallback,
              latency_ms: e.data.latency_ms,
              dissent_round: e.data.dissent_round,
            },
          ],
        }));
        break;
      case "dissent_round":
        set({ dissentRound: e.data.round_no });
        break;
      case "consensus":
        set({
          consensus: {
            text: e.data.text,
            kind: e.data.kind,
            action_list: e.data.action_list,
          },
        });
        break;
      default:
        break;
    }
  },
  endStream: () => set({ isStreaming: false }),
}));
