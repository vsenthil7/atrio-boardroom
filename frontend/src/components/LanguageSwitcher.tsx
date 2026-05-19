import { useEffect, useState } from "react";
import { apiClient } from "@/api/client";

const LANGUAGE_LABELS: Record<string, string> = {
  en: "English",
  es: "Español",
  fr: "Français",
  de: "Deutsch",
  it: "Italiano",
  pt: "Português",
  nl: "Nederlands",
  pl: "Polski",
  tr: "Türkçe",
};

interface Props {
  value: string;
  onChange: (lang: string) => void;
  disabled?: boolean;
}

export function LanguageSwitcher({ value, onChange, disabled = false }: Props): JSX.Element {
  const [supported, setSupported] = useState<string[]>(["en"]);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<{ supported_languages: string[] }>("/voice/config")
      .then((r) => {
        if (!cancelled) setSupported(r.data.supported_languages);
      })
      .catch(() => {
        // Fall back to a small default set
        if (!cancelled) setSupported(["en", "es", "fr", "de", "it"]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <label className="byline flex items-center gap-2" data-testid="language-switcher">
      <span>Lang</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="font-ui text-sm bg-transparent border border-rule px-2 py-1 disabled:opacity-50"
        data-testid="language-select"
      >
        {supported.map((l) => (
          <option key={l} value={l}>
            {LANGUAGE_LABELS[l] ?? l.toUpperCase()}
          </option>
        ))}
      </select>
    </label>
  );
}
