// Mirror of backend Pydantic schemas. Keep in sync with backend/app/api/schemas.py.

export type Role = "founder" | "authoriser" | "viewer";

export type Stance = "support" | "oppose" | "hesitate" | "unclear";

export type SessionStatus = "active" | "closed";

export type TreasuryState =
  | "proposed"
  | "first_authorised"
  | "executed"
  | "rejected"
  | "execution_failed";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  tenant_id: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Session {
  id: string;
  tenant_id: string;
  title: string | null;
  language_dominant: string;
  turn_taking_mode: string;
  status: SessionStatus;
  consensus_text: string | null;
  consensus_kind: string | null;
  boardpack_uri: string | null;
  started_at: string;
  ended_at: string | null;
}

export interface SessionList {
  items: Session[];
  next_cursor?: string | null;
}

export interface Turn {
  id: string;
  session_id: string;
  seq_no: number;
  role: "user" | "agent";
  agent_id: string | null;
  language: string;
  payload_text: string;
  tokens_in: number | null;
  tokens_out: number | null;
  latency_ms: number | null;
  model_used: string | null;
  model_was_fallback: boolean;
  prompt_version: string | null;
  dissent_round: number | null;
  confidence: string | null;
  ts: string;
}

export interface TurnList {
  items: Turn[];
}

export interface Document {
  id: string;
  session_id: string;
  filename: string;
  byte_size: number;
  sha256: string;
  kind: string;
  extraction_status: string;
  summary: string | null;
}

export interface MandateGate {
  pass: boolean;
  [key: string]: unknown;
}

export interface MandateCheckSummary {
  overall_pass: boolean;
  permitted_instruments: MandateGate;
  permitted_sides: MandateGate;
  single_instrument_max: MandateGate;
  daily_loss_limit: MandateGate;
  mandate_id?: string;
  mandate_version?: number;
}

export interface TreasuryProposal {
  id: string;
  session_id: string;
  instrument: string;
  side: "buy" | "sell";
  qty: string;
  expected_price: string | null;
  notional_eur: string;
  state: TreasuryState;
  proposed_at: string;
  expires_at: string;
  auth1_user_id: string | null;
  auth2_user_id: string | null;
  kraken_order_id: string | null;
  executed_price: string | null;
  executed_qty: string | null;
  mandate_check: MandateCheckSummary;
}

export interface Mandate {
  id: string;
  version: number;
  daily_loss_limit: string;
  single_instrument_max: string;
  permitted_instruments: string[];
  permitted_sides: string[];
  auth_user_ids: string[];
  currency: string;
  is_active: boolean;
}

export interface AuditEvent {
  id: string;
  tenant_id: string;
  session_id: string | null;
  actor_user_id: string | null;
  kind: string;
  payload_json: Record<string, unknown>;
  ts: string;
}

export interface LiveKitJoin {
  livekit_url: string;
  room: string;
  token: string;
  identity: string;
}

// ---- SSE event types (from POST /sessions/{id}/turns)
export type SSEEvent =
  | { event: "turn_started"; data: { session_id: string; seq_no: number; user_text: string } }
  | {
      event: "agent_done";
      data: {
        agent_id: string;
        text: string;
        model_used: string;
        was_fallback: boolean;
        tokens_in: number;
        tokens_out: number;
        latency_ms: number;
        stance: Stance;
        dissent_round: number | null;
      };
    }
  | { event: "dissent_round"; data: { round_no: number } }
  | {
      event: "consensus";
      data: { text: string; kind: string; action_list: Array<Record<string, unknown>> };
    }
  | {
      event: "stream_complete";
      data: { positions: Array<{ agent_id: string; stance: Stance }>; dissent_rounds: number };
    }
  | { event: "error"; data: { message: string } };

export interface ApiError {
  error: {
    code: string;
    message: string;
    request_id?: string;
    details?: Record<string, unknown>;
  };
}
