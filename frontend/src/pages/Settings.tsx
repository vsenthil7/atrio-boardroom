import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { getActiveMandate } from "@/api/extras";
import { useAuthStore } from "@/store/auth";

export function SettingsPage(): JSX.Element {
  const user = useAuthStore((s) => s.user);
  const mandate = useQuery({
    queryKey: ["mandate", "active"],
    queryFn: getActiveMandate,
    retry: false,
  });
  const voiceConfig = useQuery({
    queryKey: ["voice", "config"],
    queryFn: async () => {
      const r = await apiClient.get<{
        supported_languages: string[];
        default_language: string;
        custom_dictionary_size: number;
      }>("/voice/config");
      return r.data;
    },
  });

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <section className="border-b border-rule pb-6 mb-8">
        <div className="byline">Account · Mandate · Voice</div>
        <h2 className="masthead">Settings</h2>
      </section>

      <div className="grid lg:grid-cols-2 gap-8">
        <section data-testid="settings-account">
          <h3 className="byline mb-3">Account</h3>
          <dl className="card p-5 font-ui text-sm space-y-2">
            <Row k="Display name" v={user?.display_name ?? "—"} />
            <Row k="Email" v={user?.email ?? "—"} />
            <Row k="Role" v={user?.role ?? "—"} />
            <Row k="Tenant" v={user?.tenant_id?.slice(0, 8) ?? "—"} />
          </dl>
        </section>

        <section data-testid="settings-mandate">
          <h3 className="byline mb-3">Active mandate</h3>
          {mandate.isLoading && <p className="font-ui text-sub">Loading…</p>}
          {mandate.isError && (
            <p className="font-display italic text-sub card p-5">
              No active mandate.
            </p>
          )}
          {mandate.data && (
            <dl className="card p-5 font-ui text-sm space-y-2">
              <Row k="Version" v={`v${mandate.data.version}`} />
              <Row
                k="Daily loss limit"
                v={`${mandate.data.currency} ${mandate.data.daily_loss_limit}`}
              />
              <Row
                k="Single-instrument max"
                v={`${mandate.data.currency} ${mandate.data.single_instrument_max}`}
              />
              <Row
                k="Instruments"
                v={mandate.data.permitted_instruments.join(", ")}
              />
              <Row k="Sides" v={mandate.data.permitted_sides.join(", ")} />
              <Row k="Authorisers" v={String(mandate.data.auth_user_ids.length)} />
            </dl>
          )}
        </section>

        <section data-testid="settings-voice">
          <h3 className="byline mb-3">Voice & language</h3>
          {voiceConfig.isLoading && <p className="font-ui text-sub">Loading…</p>}
          {voiceConfig.data && (
            <dl className="card p-5 font-ui text-sm space-y-2">
              <Row k="Default language" v={voiceConfig.data.default_language} />
              <Row
                k="Supported languages"
                v={voiceConfig.data.supported_languages.join(", ")}
              />
              <Row
                k="Custom dictionary"
                v={`${voiceConfig.data.custom_dictionary_size} terms`}
              />
            </dl>
          )}
        </section>

        <section data-testid="settings-product">
          <h3 className="byline mb-3">Product</h3>
          <dl className="card p-5 font-ui text-sm space-y-2">
            <Row k="Build" v="ATRIO Boardroom v1.0.0" />
            <Row k="Mode" v="Paper trading · mock inference fallback" />
            <Row k="License" v="Apache 2.0" />
          </dl>
        </section>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between border-b border-rule py-1 gap-3">
      <dt className="text-sub uppercase tracking-wider text-xs">{k}</dt>
      <dd className="text-right font-display break-words">{v}</dd>
    </div>
  );
}
