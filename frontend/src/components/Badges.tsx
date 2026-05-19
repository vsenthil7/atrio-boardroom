import type { Stance } from "@/types";

export function StanceBadge({ stance }: { stance: Stance }): JSX.Element {
  const cls =
    stance === "support"
      ? "badge-support"
      : stance === "oppose"
        ? "badge-oppose"
        : stance === "hesitate"
          ? "badge-hesitate"
          : "badge-unclear";
  return <span className={cls} data-testid={`stance-${stance}`}>{stance}</span>;
}

const AGENT_LABELS: Record<string, string> = {
  facilitator: "Facilitator",
  cfo: "CFO",
  cto: "CTO",
  cmo: "CMO",
  coo: "COO",
  counsel: "Counsel",
  treasury: "Treasury",
};

export function AgentBadge({ agentId }: { agentId: string }): JSX.Element {
  const label = AGENT_LABELS[agentId] ?? agentId.toUpperCase();
  return (
    <span className="font-ui text-xs uppercase tracking-widest text-sub border border-rule px-2 py-0.5">
      {label}
    </span>
  );
}
