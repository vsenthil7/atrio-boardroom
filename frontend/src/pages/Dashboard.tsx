import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createSession, listSessions } from "@/api/sessions";
import { apiErrorMessage } from "@/api/client";

export function DashboardPage(): JSX.Element {
  const { data, isLoading, error } = useQuery({
    queryKey: ["sessions"],
    queryFn: listSessions,
  });
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [title, setTitle] = useState("");

  const mutation = useMutation({
    mutationFn: createSession,
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      navigate(`/sessions/${s.id}`);
    },
  });

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <section className="border-b border-rule pb-8 mb-10">
        <h2 className="masthead mb-2">Sessions</h2>
        <p className="deck">Open a new boardroom or revisit a previous one.</p>
      </section>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({ title: title || undefined });
          setTitle("");
        }}
        className="grid grid-cols-1 md:grid-cols-[1fr,auto] gap-3 mb-10"
      >
        <input
          data-testid="new-session-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="What's on the table?"
          className="border-b-2 border-ink bg-transparent py-3 font-display text-2xl placeholder:text-rule focus:outline-none focus:border-accent"
        />
        <button
          type="submit"
          data-testid="new-session-submit"
          disabled={mutation.isPending}
          className="btn-primary self-end"
        >
          {mutation.isPending ? "Opening…" : "Open session"}
        </button>
      </form>

      {error && (
        <p className="mb-6 border border-accent bg-accent/10 p-3 font-ui text-sm text-accent">
          {apiErrorMessage(error)}
        </p>
      )}

      {isLoading ? (
        <p className="font-ui text-sub">Loading…</p>
      ) : (
        <ul className="divide-y divide-rule" data-testid="sessions-list">
          {(data?.items ?? []).length === 0 && (
            <li className="font-display italic text-sub py-8">
              No sessions yet. Start the first one above.
            </li>
          )}
          {(data?.items ?? []).map((s) => (
            <li
              key={s.id}
              data-testid="session-row"
              onClick={() => navigate(`/sessions/${s.id}`)}
              className="py-6 cursor-pointer hover:bg-muted/50 transition-colors px-3 -mx-3"
            >
              <div className="flex items-baseline justify-between gap-6">
                <h3 className="font-display text-2xl font-semibold">
                  {s.title || "Untitled session"}
                </h3>
                <span className="byline">
                  {new Date(s.started_at).toLocaleString("en-GB")} ·{" "}
                  {s.status === "closed" ? (
                    <em className="not-italic text-gold">closed</em>
                  ) : (
                    <em className="not-italic text-accent">active</em>
                  )}
                </span>
              </div>
              {s.consensus_text && (
                <p className="mt-2 font-display italic text-sub max-w-3xl line-clamp-2">
                  {s.consensus_text}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
