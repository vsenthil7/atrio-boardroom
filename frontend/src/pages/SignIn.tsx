import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  consumeMagicLink,
  devSignin,
  getDevSigninStatus,
  me,
  requestMagicLink,
} from "@/api/auth";
import { apiErrorMessage } from "@/api/client";
import { useAuthStore } from "@/store/auth";

type Stage = "request" | "consume";

// Demo accounts seeded by /api/v1/_test/seed-demo. The "Sign in with one click"
// panel is shown when the API reports demo-mode enabled. On a real production
// deploy (env not configured for demo), this panel hides itself.
const DEMO_USERS: { label: string; email: string; role: string }[] = [
  { label: "Demo founder", email: "founder@acme.co", role: "founder · proposes treasury actions" },
  { label: "Demo CEO", email: "ceo@acme.co", role: "CEO · second-signs for two-party auth" },
];

export function SignInPage(): JSX.Element {
  const [stage, setStage] = useState<Stage>("request");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [demoEnabled, setDemoEnabled] = useState(false);
  const { setTokens, setUser } = useAuthStore();
  const navigate = useNavigate();

  // Probe whether judge-mode is enabled on this API.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await getDevSigninStatus();
        if (!cancelled && s.enabled) {
          setDemoEnabled(true);
        }
      } catch {
        // ignore -- if the probe fails, just don't show the panel
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function oneClickDemoSignin(emailToUse: string) {
    setError(null);
    setLoading(true);
    try {
      const tok = await devSignin(emailToUse);
      setTokens(tok.access_token, tok.refresh_token);
      const u = await me();
      setUser(u);
      navigate("/", { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function onRequest(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const r = await requestMagicLink(email);
      if (r.dev_token) {
        // Dev/test/demo mode: token returned inline. Pre-fill for one-click sign-in.
        setToken(r.dev_token);
      }
      setStage("consume");
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function onConsume(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const tok = await consumeMagicLink(token);
      setTokens(tok.access_token, tok.refresh_token);
      const u = await me();
      setUser(u);
      navigate("/", { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Left: editorial poster */}
      <aside className="hidden lg:flex flex-col justify-between p-12 border-r border-ink bg-ink text-paper">
        <header className="font-ui text-xs uppercase tracking-widest">
          Vol. I · No. 1 · Milan AI Week 2026
        </header>
        <div>
          <h1 className="font-display text-7xl font-bold leading-none mb-4">
            Your<br />AI<br />Boardroom.
          </h1>
          <p className="font-display italic text-2xl text-paper/80 max-w-md">
            Six agents. One table. Audit-grade by default.
          </p>
        </div>
        <ul className="font-ui text-sm space-y-1 text-paper/60">
          <li>· Voice-first multilingual</li>
          <li>· Mandate-enforced treasury</li>
          <li>· Two-party authorisation</li>
        </ul>
      </aside>

      {/* Right: sign-in form */}
      <section className="flex items-center justify-center p-8 lg:p-16">
        <div className="w-full max-w-md">
          <h2 className="font-display text-4xl font-bold mb-2">Sign in</h2>
          <p className="font-display italic text-sub mb-10">
            {demoEnabled
              ? "Sign in with one click below, or use your own email."
              : "A magic link will be sent to your email."}
          </p>

          {/* Demo-user one-click panel — auto-detected via /auth/dev-signin probe. */}
          {demoEnabled && stage === "request" && (
            <div
              data-testid="demo-panel"
              className="mb-8 border-2 border-ink bg-muted/50 p-5"
            >
              <p className="byline mb-3">Judges · sign in with one click</p>
              <div className="space-y-2">
                {DEMO_USERS.map((u) => (
                  <button
                    key={u.email}
                    type="button"
                    onClick={() => oneClickDemoSignin(u.email)}
                    disabled={loading}
                    data-testid={`demo-signin-${u.email.split("@")[0]}`}
                    className="w-full text-left border border-ink bg-paper px-4 py-3 hover:bg-ink hover:text-paper transition-colors disabled:opacity-50"
                  >
                    <span className="font-display text-lg font-bold block">{u.label}</span>
                    <span className="font-ui text-xs opacity-70">{u.role}</span>
                  </button>
                ))}
              </div>
              <p className="font-ui text-xs text-sub mt-3 italic">
                Or use your own email below to receive a magic link.
              </p>
            </div>
          )}

          {stage === "request" && (
            <form onSubmit={onRequest} className="space-y-5">
              <label className="block">
                <span className="byline mb-2 block">Email</span>
                <input
                  data-testid="email-input"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full border-b-2 border-ink bg-transparent py-2 font-display text-xl placeholder:text-rule focus:outline-none focus:border-accent"
                  placeholder="you@company.com"
                  autoComplete="email"
                />
              </label>
              <button
                type="submit"
                data-testid="request-magic-link"
                disabled={loading}
                className="btn-primary w-full disabled:opacity-50"
              >
                {loading ? "Sending…" : "Send magic link"}
              </button>
            </form>
          )}

          {stage === "consume" && (
            <form onSubmit={onConsume} className="space-y-5">
              <label className="block">
                <span className="byline mb-2 block">Magic-link token</span>
                <textarea
                  data-testid="token-input"
                  required
                  rows={4}
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  className="w-full border border-rule bg-muted/40 p-3 font-mono text-xs focus:outline-none focus:border-ink"
                  placeholder="paste the token from your email"
                />
              </label>
              <button
                type="submit"
                data-testid="consume-token"
                disabled={loading}
                className="btn-primary w-full disabled:opacity-50"
              >
                {loading ? "Signing in…" : "Sign in"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setStage("request");
                  setToken("");
                }}
                className="text-sub underline underline-offset-4 text-sm font-ui"
              >
                Use a different email
              </button>
            </form>
          )}

          {error && (
            <p
              data-testid="signin-error"
              className="mt-6 border border-accent bg-accent/10 p-3 font-ui text-sm text-accent"
            >
              {error}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
