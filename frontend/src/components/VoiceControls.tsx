import { useLiveKit } from "@/hooks/useLiveKit";

interface Props {
  sessionId: string;
  disabled?: boolean;
}

export function VoiceControls({ sessionId, disabled = false }: Props): JSX.Element {
  const { isConnected, isConnecting, error, participants, captions, micEnabled, connect, disconnect, toggleMic } =
    useLiveKit(sessionId);

  return (
    <section className="border-t border-rule pt-6" data-testid="voice-controls">
      <h3 className="byline mb-2">Voice</h3>
      {!isConnected ? (
        <button
          onClick={connect}
          disabled={disabled || isConnecting}
          className="btn-secondary w-full disabled:opacity-50"
          data-testid="voice-join"
        >
          {isConnecting ? "Connecting…" : "Join voice"}
        </button>
      ) : (
        <div className="space-y-3">
          <div className="flex gap-2">
            <button
              onClick={toggleMic}
              className={`btn-secondary flex-1 ${micEnabled ? "bg-ink text-paper" : ""}`}
              data-testid="voice-mic-toggle"
            >
              {micEnabled ? "🎤 Mic on" : "Mic off"}
            </button>
            <button
              onClick={disconnect}
              className="btn-secondary"
              data-testid="voice-leave"
            >
              Leave
            </button>
          </div>
          <ul className="font-ui text-xs text-sub space-y-0.5" data-testid="voice-participants">
            {participants.map((p) => (
              <li key={p}>· {p}</li>
            ))}
          </ul>
        </div>
      )}
      {error && (
        <p
          className="mt-2 border border-accent bg-accent/10 p-2 font-ui text-xs text-accent"
          data-testid="voice-error"
        >
          {error}
        </p>
      )}
      {captions.length > 0 && (
        <div className="mt-4 border-t border-rule pt-3">
          <h4 className="byline mb-1">Live captions</h4>
          <ul
            className="font-display text-sm space-y-1 max-h-40 overflow-y-auto"
            data-testid="voice-captions"
          >
            {captions.slice(-6).map((c) => (
              <li
                key={c.id}
                className={c.isFinal ? "text-ink" : "text-sub italic"}
                data-testid="voice-caption"
              >
                <span className="byline">{c.speaker.slice(0, 8)}:</span> {c.text}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
