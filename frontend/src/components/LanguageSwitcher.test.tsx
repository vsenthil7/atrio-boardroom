import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LanguageSwitcher } from "./LanguageSwitcher";

const mockGet = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

describe("LanguageSwitcher", () => {
  beforeEach(() => {
    mockGet.mockReset();
  });
  afterEach(() => {
    mockGet.mockReset();
  });

  it("renders the default language when API hasn't responded yet", () => {
    mockGet.mockReturnValue(new Promise(() => undefined));
    render(<LanguageSwitcher value="en" onChange={() => undefined} />);
    expect(screen.getByTestId("language-switcher")).toBeInTheDocument();
    expect(screen.getByTestId("language-select")).toHaveValue("en");
  });

  it("populates options once the API returns", async () => {
    mockGet.mockResolvedValueOnce({
      data: { supported_languages: ["en", "es", "fr"] },
    });
    render(<LanguageSwitcher value="en" onChange={() => undefined} />);
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Español" })).toBeInTheDocument();
    });
  });

  it("falls back to a default set when the API fails", async () => {
    mockGet.mockRejectedValueOnce(new Error("boom"));
    render(<LanguageSwitcher value="en" onChange={() => undefined} />);
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Español" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Italiano" })).toBeInTheDocument();
    });
  });

  it("calls onChange when a language is picked", async () => {
    mockGet.mockResolvedValueOnce({ data: { supported_languages: ["en", "es", "de"] } });
    const onChange = vi.fn();
    render(<LanguageSwitcher value="en" onChange={onChange} />);
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Deutsch" })).toBeInTheDocument(),
    );
    await userEvent.selectOptions(screen.getByTestId("language-select"), "de");
    expect(onChange).toHaveBeenCalledWith("de");
  });

  it("respects the disabled prop", () => {
    mockGet.mockReturnValue(new Promise(() => undefined));
    render(<LanguageSwitcher value="en" onChange={() => undefined} disabled />);
    expect(screen.getByTestId("language-select")).toBeDisabled();
  });
});
