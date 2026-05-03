export type AgentKey = 'detection' | 'analysis' | 'decision' | 'communication' | 'action';
export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type AgentStatus = 'idle' | 'running' | 'completed' | 'failed';

export interface AgentCost {
  input: number;
  output: number;
}

export interface Exception {
  id: number;
  tracking_number: string;
  carrier: string;
  customer_name?: string;
  exception_type: string;
  severity: Severity | null;
  workflow_status: string;
  detected_at: string;
  shipment_id?: number;
  source: string;
  location: string | null;
  agent_statuses: Record<AgentKey, AgentStatus>;
  agent_outputs: Record<AgentKey, any>;
  agent_durations: Partial<Record<AgentKey, number>>;
  agent_costs: Partial<Record<AgentKey, AgentCost>>;
  resolution_type: string | null;
  description?: string;
}

export interface AgentDef {
  key: AgentKey;
  label: string;
  color: string;
}

export const AGENTS: AgentDef[] = [
  { key: 'detection',     label: 'Detection',     color: 'blue' },
  { key: 'analysis',      label: 'Analysis',      color: 'violet' },
  { key: 'decision',      label: 'Decision',      color: 'amber' },
  { key: 'communication', label: 'Communication', color: 'emerald' },
  { key: 'action',        label: 'Action',        color: 'rose' },
];

export interface AgentStat extends AgentDef {
  runs: number;
  successes: number;
  failures: number;
  successRate: number | null;
  costUsd: number;
}

export interface TotalStats {
  resolved: number;
  failed: number;
  active: number;
  bySeverity: Record<string, number>;
  byType: Record<string, number>;
  byResolution: Record<string, number>;
  totalCost: number;
  totalInput: number;
  totalOutput: number;
  agentStats: AgentStat[];
}
