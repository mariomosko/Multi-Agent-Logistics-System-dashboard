import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AGENTS, AgentDef, TotalStats } from '../../models/exception.model';

const CIN  = 0.000003;
const COUT = 0.000015;

const AGENT_BAR_COLORS: Record<string, string> = {
  blue: 'bg-blue-400', violet: 'bg-violet-400', amber: 'bg-amber-400',
  emerald: 'bg-emerald-400', rose: 'bg-rose-400',
};

@Component({
  selector: 'app-cost-tracker',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './cost-tracker.component.html',
})
export class CostTrackerComponent {
  @Input() stats!: TotalStats;

  agents: AgentDef[] = AGENTS;

  get totalCost():   number { return this.stats?.totalCost   ?? 0; }
  get totalInput():  number { return this.stats?.totalInput  ?? 0; }
  get totalOutput(): number { return this.stats?.totalOutput ?? 0; }
  get resolved():    number { return this.stats?.resolved    ?? 0; }

  get apiCalls():      number { return (this.stats?.agentStats ?? []).reduce((s, a) => s + a.runs, 0); }
  get avgCostPerEx():  number { return this.resolved > 0 ? this.totalCost / this.resolved : 0; }
  get maxAgentCost():  number { return Math.max(...(this.stats?.agentStats ?? []).map(a => a.costUsd), 0.000001); }
  get hasTokens():     boolean { return (this.totalInput + this.totalOutput) > 0; }

  inputPct():  number { return this.hasTokens ? (this.totalInput  / (this.totalInput + this.totalOutput)) * 100 : 50; }
  outputPct(): number { return this.hasTokens ? (this.totalOutput / (this.totalInput + this.totalOutput)) * 100 : 50; }

  agentCost(key: string): number { return this.stats?.agentStats.find(s => s.key === key)?.costUsd ?? 0; }
  agentBarPct(key: string): number { return this.maxAgentCost > 0 ? (this.agentCost(key) / this.maxAgentCost) * 100 : 0; }
  agentBarColor(color: string): string { return AGENT_BAR_COLORS[color] ?? 'bg-gray-400'; }

  inputCostDisplay():  string { return (this.totalInput  * CIN ).toFixed(4); }
  outputCostDisplay(): string { return (this.totalOutput * COUT).toFixed(4); }
  inputPctLabel():     string { return Math.round(this.inputPct())  + '% input'; }
  outputPctLabel():    string { return Math.round(this.outputPct()) + '% output'; }
}
