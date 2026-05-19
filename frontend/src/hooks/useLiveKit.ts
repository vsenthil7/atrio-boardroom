import { useCallback, useEffect, useRef, useState } from "react";
import {
  ConnectionState,
  type LocalParticipant,
  type RemoteParticipant,
  Room,
  RoomEvent,
  Track,
  type TrackPublication,
} from "livekit-client";
import { joinVoice } from "@/api/extras";

export interface Caption {
  id: string;
  speaker: string;
  text: string;
  isFinal: boolean;
  language: string;
  ts: number;
}

export interface UseLiveKitResult {
  state: ConnectionState;
  isConnecting: boolean;
  isConnected: boolean;
  error: string | null;
  participants: string[];
  captions: Caption[];
  micEnabled: boolean;
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  toggleMic: () => Promise<void>;
}

/**
 * LiveKit hook for joining a voice session.
 *
 * - Requests a join token from the backend (which issues a short-lived JWT).
 * - Connects to the LiveKit room, publishes the local mic track.
 * - Subscribes to data messages on the "captions" topic for live transcripts.
 * - Cleans up on unmount.
 */
export function useLiveKit(sessionId: string | null): UseLiveKitResult {
  const [state, setState] = useState<ConnectionState>(ConnectionState.Disconnected);
  const [error, setError] = useState<string | null>(null);
  const [participants, setParticipants] = useState<string[]>([]);
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [micEnabled, setMicEnabled] = useState(false);

  const roomRef = useRef<Room | null>(null);

  const updateParticipants = useCallback((room: Room) => {
    const names: string[] = [];
    if (room.localParticipant) names.push(room.localParticipant.identity);
    room.remoteParticipants.forEach((p: RemoteParticipant) => names.push(p.identity));
    setParticipants(names);
  }, []);

  const handleDataReceived = useCallback(
    (payload: Uint8Array, participant?: RemoteParticipant | LocalParticipant) => {
      try {
        const text = new TextDecoder().decode(payload);
        const msg = JSON.parse(text);
        if (msg?.kind === "caption") {
          const speaker = participant?.identity ?? msg.speaker ?? "unknown";
          setCaptions((prev) => {
            const next: Caption = {
              id: msg.id ?? `c-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              speaker,
              text: msg.text ?? "",
              isFinal: !!msg.is_final,
              language: msg.language ?? "en",
              ts: Date.now(),
            };
            // For partials, replace the most recent partial from this speaker
            if (!next.isFinal) {
              const idx = prev.findIndex((c) => c.speaker === speaker && !c.isFinal);
              if (idx >= 0) {
                const copy = [...prev];
                copy[idx] = next;
                return copy;
              }
            }
            // Drop trailing partial when we get the final
            const stripped = prev.filter((c) => !(c.speaker === speaker && !c.isFinal));
            return [...stripped, next].slice(-50); // keep last 50
          });
        }
      } catch {
        // ignore malformed data
      }
    },
    [],
  );

  const connect = useCallback(async () => {
    if (!sessionId) {
      setError("no session selected");
      return;
    }
    if (roomRef.current) return; // already connected
    setError(null);
    setState(ConnectionState.Connecting);
    try {
      const join = await joinVoice(sessionId);
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });
      roomRef.current = room;

      room.on(RoomEvent.ConnectionStateChanged, (s) => setState(s));
      room.on(RoomEvent.ParticipantConnected, () => updateParticipants(room));
      room.on(RoomEvent.ParticipantDisconnected, () => updateParticipants(room));
      room.on(RoomEvent.DataReceived, handleDataReceived);
      room.on(RoomEvent.Disconnected, () => {
        setState(ConnectionState.Disconnected);
        setParticipants([]);
        setMicEnabled(false);
        roomRef.current = null;
      });

      await room.connect(join.livekit_url, join.token);
      // Enable mic publishing by default
      try {
        await room.localParticipant.setMicrophoneEnabled(true);
        setMicEnabled(true);
      } catch (err) {
        // Mic permission denied — still connect, captions still work
        console.warn("mic permission denied:", err);
      }
      updateParticipants(room);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "connection failed";
      setError(msg);
      setState(ConnectionState.Disconnected);
      roomRef.current = null;
    }
  }, [sessionId, handleDataReceived, updateParticipants]);

  const disconnect = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    await room.disconnect();
    roomRef.current = null;
    setMicEnabled(false);
    setParticipants([]);
  }, []);

  const toggleMic = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    const next = !micEnabled;
    await room.localParticipant.setMicrophoneEnabled(next);
    setMicEnabled(next);
  }, [micEnabled]);

  useEffect(() => {
    return () => {
      void roomRef.current?.disconnect();
      roomRef.current = null;
    };
  }, []);

  // Helper exports
  void Track;
  void (null as TrackPublication | null);

  return {
    state,
    isConnecting: state === ConnectionState.Connecting,
    isConnected: state === ConnectionState.Connected,
    error,
    participants,
    captions,
    micEnabled,
    connect,
    disconnect,
    toggleMic,
  };
}
