import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AGENTS, AgentDef, AgentStat, Exception } from '../../models/exception.model';

const COLOR_RING: Record<string, string> = {
  blue: 'ring-blue-400 bg-blue-50', violet: 'ring-violet-400 bg-violet-50',
  amber: 'ring-amber-400 bg-amber-50', emerald: 'ring-emerald-400 bg-emerald-50', rose: 'ring-rose-400 bg-rose-50',
};
const COLOR_DOT: Record<string, string> = {
  blue: 'bg-blue-400', violet: 'bg-violet-400', amber: 'bg-amber-400', emerald: 'bg-emerald-400', rose: 'bg-rose-400',
};
const COLOR_TEXT: Record<string, string> = {
  blue: 'text-blue-600', violet: 'text-violet-600', amber: 'text-amber-600', emerald: 'text-emerald-600', rose: 'text-rose-600',
};

@Component({
  selector: 'app-agent-pipeline',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './agent-pipeline.component.html',
})
export class AgentPipelineComponent {
  @Input() exceptions: Exception[] = [];
  @Input() agentStats: AgentStat[] = [];

  agents: AgentDef[] = AGENTS;

  runningCount(key: string): number {
    return this.exceptions.filter(e => (e.agent_statuses as any)[key] === 'running').length;
  }

  isActive(key: string): boolean { return this.runningCount(key) > 0; }

  statFor(key: string): AgentStat | undefined {
    return this.agentStats.find(s => s.key === key);
  }

  cardClass(key: string, color: string): string {
    return this.isActive(key)
      ? `flex-1 rounded-xl border-2 p-3 transition-all ring-2 ${COLOR_RING[color]}`
      : 'flex-1 rounded-xl border-2 border-gray-100 bg-white p-3 transition-all';
  }

  dotClass(key: string, color: string): string {
    return this.isActive(key)
      ? `w-2 h-2 rounded-full ${COLOR_DOT[color]} animate-pulse`
      : 'w-2 h-2 rounded-full bg-gray-200';
  }

  labelClass(key: string, color: string): string {
    return `text-xs font-semibold ${this.isActive(key) ? COLOR_TEXT[color] : 'text-gray-500'}`;
  }

  activeTextClass(color: string): string {
    return `text-xs font-medium mb-2 ${COLOR_TEXT[color]}`;
  }

  successRateClass(rate: number | null | undefined): string {
    if (rate == null) return 'font-medium text-gray-400';
    return rate >= 90 ? 'font-medium text-green-600'
         : rate >= 70 ? 'font-medium text-yellow-600'
         : 'font-medium text-red-500';
  }
}
