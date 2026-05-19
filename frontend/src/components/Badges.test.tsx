import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentBadge, StanceBadge } from "./Badges";

describe("Badges", () => {
  it("renders stance badge with the right test id", () => {
    render(<StanceBadge stance="support" />);
    expect(screen.getByTestId("stance-support")).toHaveTextContent("support");
  });

  it("renders all stances", () => {
    const stances = ["support", "oppose", "hesitate", "unclear"] as const;
    for (const s of stances) {
      const { unmount } = render(<StanceBadge stance={s} />);
      expect(screen.getByTestId(`stance-${s}`)).toBeInTheDocument();
      unmount();
    }
  });

  it("renders friendly agent labels", () => {
    render(<AgentBadge agentId="cfo" />);
    expect(screen.getByText("CFO")).toBeInTheDocument();
  });

  it("falls back to uppercased id for unknown agents", () => {
    render(<AgentBadge agentId="mystery" />);
    expect(screen.getByText("MYSTERY")).toBeInTheDocument();
  });
});
