import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  boardpackUrl,
  closeSession,
  getSession,
  listTurns,
} from "@/api/sessions";
import { listDocuments, uploadDocument } from "@/api/documents";
import { streamTurn } from "@/api/turns";
import { useAuthStore } from "@/store/auth";
import { useSessionStore } from "@/store/session";
import { apiErrorMessage } from "@/api/client";
import { AgentBadge, StanceBadge } from "@/components/Badges";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { VoiceControls } from "@/components/VoiceControls";

export function WorkspacePage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const token = useAuthStore((s) => s.accessToken);
  const {
    setCurrentSession,
    setTurns,
    beginStream,
    applyEvent,
    endStream,
    positions,
    consensus,
    isStreaming,
    dissentRound,
  } = useSessionStore();
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<"single" | "debate">("debate");
  const [language, setLanguage] = useState<string>("en");
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const session = useQuery({
    queryKey: ["session", id],
    queryFn: () => getSession(id!),
    enabled: !!id,
  });
  const turns = useQuery({
    queryKey: ["turns", id],
    queryFn: () => listTurns(id!),
    enabled: !!id,
  });
  const docs = useQuery({
    queryKey: ["docs", id],
    queryFn: () => listDocuments(id!),
    enabled: !!id,
  });

  useEffect(() => {
    if (id) setCurrentSession(id);
  }, [id, setCurrentSession]);

  useEffect(() => {
    if (turns.data) setTurns(turns.data.items);
  }, [turns.data, setTurns]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [positions.length, consensus]);

  const closeMut = useMutation({
    mutationFn: () => closeSession(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["session", id] });
    },
  });

  const uploadMut = useMutation({
    mutationFn: (file: File) => uploadDocument(id!, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["docs", id] }),
  });

  useEffect(() => {
    if (session.data?.language_dominant) setLanguage(session.data.language_dominant);
  }, [session.data?.language_dominant]);

  async function onAsk(e: React.FormEvent) {
    e.preventDefault();
    if (!id || !token || !draft.trim()) return;
    setError(null);
    beginStream();
    try {
      await streamTurn({
        sessionId: id,
        accessToken: token,
        text: draft,
        language,
        mode,
        onEvent: applyEvent,
      });
      setDraft("");
      await qc.invalidateQueries({ queryKey: ["turns", id] });
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      endStream();
    }
  }

  if (!id) return <div className="p-8">No session id.</div>;
  if (session.isLoading) return <div className="p-8">Loading…</div>;
  if (session.error)
    return <div className="p-8 text-accent">{apiErrorMessage(session.error)}</div>;

  const s = session.data!;
  const isClosed = s.status === "closed";

  return (
    <div className="max-w-7xl mx-auto px-6 py-10 grid lg:grid-cols-[1fr,300px] gap-10">
      <div className="min-w-0">
        <section className="border-b border-rule pb-6 mb-8">
          <div className="byline mb-2">
            Session · {new Date(s.started_at).toLocaleString("en-GB")}
          </div>
          <h2 className="masthead">{s.title || "Untitled"}</h2>
          {s.consensus_text && (
            <p className="deck mt-3">{s.consensus_text}</p>
          )}
        </section>

        <div
          ref={scrollRef}
          className="space-y-8 mb-10 max-h-[60vh] overflow-y-auto pr-2"
          data-testid="turn-feed"
        >
          {turns.data?.items.map((t) => (
            <article
              key={t.id}
              className={`animate-fade-in ${t.role === "user" ? "" : "pl-8 border-l-2 border-rule"}`}
              data-testid={`turn-${t.seq_no}`}
            >
              <header className="flex items-center gap-3 mb-2">
                {t.role === "user" ? (
                  <span className="byline">You</span>
                ) : (
                  <>
                    <AgentBadge agentId={t.agent_id || "agent"} />
                    {t.dissent_round && (
                      <span className="font-ui text-xs uppercase tracking-widest text-accent">
                        Dissent round {t.dissent_round}
                      </span>
                    )}
                  </>
                )}
                <span className="byline">{new Date(t.ts).toLocaleTimeString("en-GB")}</span>
              </header>
              <p className="font-display text-lg leading-relaxed">{t.payload_text}</p>
            </article>
          ))}

          {/* Live streaming positions */}
          {positions.map((p, idx) => (
            <article
              key={`live-${idx}`}
              className="animate-fade-in pl-8 border-l-2 border-accent"
              data-testid="streaming-position"
            >
              <header className="flex items-center gap-3 mb-2">
                <AgentBadge agentId={p.agent_id} />
                <StanceBadge stance={p.stance} />
                {p.dissent_round && (
                  <span className="font-ui text-xs uppercase tracking-widest text-accent">
                    Dissent round {p.dissent_round}
                  </span>
                )}
                {p.was_fallback && (
                  <span className="byline text-accent">↺ fallback</span>
                )}
              </header>
              <p className="font-display text-lg leading-relaxed">{p.text}</p>
            </article>
          ))}

          {isStreaming && (
            <p
              className="font-ui text-sm text-sub animate-stream-pulse"
              data-testid="streaming-indicator"
            >
              · · · the board is debating
              {dissentRound ? ` (dissent round ${dissentRound})` : ""}
            </p>
          )}

          {consensus && (
            <section
              className="rule-bold pt-6 mt-8"
              data-testid="consensus-card"
            >
              <div className="byline mb-2">
                Consensus · {consensus.kind}
              </div>
              <p className="font-display text-2xl">{consensus.text}</p>
              {Array.isArray(consensus.action_list) && consensus.action_list.length > 0 && (
                <ol className="mt-4 font-display text-base list-decimal pl-6 space-y-1">
                  {consensus.action_list.map((a, i) => (
                    <li key={i}>{(a as { description?: string }).description}</li>
                  ))}
                </ol>
              )}
            </section>
          )}
        </div>

        {error && (
          <p className="mb-4 border border-accent bg-accent/10 p-3 font-ui text-sm text-accent">
            {error}
          </p>
        )}

        {!isClosed ? (
          <form onSubmit={onAsk} className="space-y-3">
            <textarea
              data-testid="turn-input"
              rows={3}
              placeholder="Ask the boardroom…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={isStreaming}
              className="w-full border-2 border-ink bg-transparent p-3 font-display text-lg placeholder:text-rule focus:outline-none focus:border-accent disabled:opacity-50"
            />
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-4 flex-wrap">
                <label className="byline flex items-center gap-3">
                  Mode
                  <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value as "single" | "debate")}
                    className="font-ui text-sm bg-transparent border border-rule px-2 py-1"
                    data-testid="mode-select"
                  >
                    <option value="debate">Full debate</option>
                    <option value="single">Quick read</option>
                  </select>
                </label>
                <LanguageSwitcher value={language} onChange={setLanguage} disabled={isStreaming} />
              </div>
              <div className="flex gap-3">
                <button
                  type="submit"
                  data-testid="ask-submit"
                  disabled={isStreaming || !draft.trim()}
                  className="btn-primary disabled:opacity-50"
                >
                  {isStreaming ? "Streaming…" : "Ask"}
                </button>
              </div>
            </div>
          </form>
        ) : (
          <p className="font-display italic text-sub border-t-2 border-ink pt-6">
            This session is closed. Open a new one to continue.
          </p>
        )}
      </div>

      {/* sidebar */}
      <aside className="space-y-6 lg:sticky lg:top-6 self-start">
        <section>
          <h3 className="byline mb-2">Documents</h3>
          <UploadDropzone
            disabled={isClosed}
            onFile={(f) => uploadMut.mutate(f)}
            pending={uploadMut.isPending}
          />
          <ul className="mt-3 text-sm font-ui space-y-1">
            {docs.data?.map((d) => (
              <li key={d.id} data-testid="doc-row" className="border-b border-rule py-1">
                <div className="truncate font-display">{d.filename}</div>
                <div className="byline">
                  {d.kind} · {(d.byte_size / 1024).toFixed(1)}kB · {d.extraction_status}
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="border-t border-rule pt-6">
          <h3 className="byline mb-2">Actions</h3>
          <div className="space-y-2">
            {!isClosed && (
              <button
                onClick={() => closeMut.mutate()}
                disabled={closeMut.isPending}
                data-testid="close-session"
                className="btn-secondary w-full"
              >
                {closeMut.isPending ? "Closing…" : "Close session"}
              </button>
            )}
            <a
              href={boardpackUrl(id)}
              data-testid="download-boardpack"
              className="btn-secondary w-full"
              target="_blank"
              rel="noreferrer"
            >
              Download boardpack
            </a>
            <button
              onClick={() => navigate("/treasury")}
              className="btn-secondary w-full"
            >
              Open treasury
            </button>
          </div>
        </section>

        <VoiceControls sessionId={id} disabled={isClosed} />
      </aside>
    </div>
  );
}

function UploadDropzone({
  onFile,
  pending,
  disabled,
}: {
  onFile: (f: File) => void;
  pending: boolean;
  disabled: boolean;
}): JSX.Element {
  return (
    <label
      className={`block border-2 border-dashed border-rule p-4 text-center font-ui text-sm text-sub cursor-pointer hover:border-ink transition-colors ${
        disabled ? "opacity-50 pointer-events-none" : ""
      }`}
    >
      <input
        type="file"
        data-testid="doc-upload"
        className="sr-only"
        disabled={disabled || pending}
        accept=".pdf,.docx,.xlsx,.png,.jpg,.jpeg"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.currentTarget.value = "";
        }}
      />
      {pending ? "Uploading…" : "Drop file or click — pdf · docx · xlsx · png · jpg"}
    </label>
  );
}
