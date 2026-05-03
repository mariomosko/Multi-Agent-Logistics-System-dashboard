import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AGENTS, AgentDef, Exception } from '../../models/exception.model';
import { ApiService, normalizeDetail } from '../../services/api.service';

const SEV: Record<string, any> = {
  critical: { stripe: 'bg-red-500',    border: 'border-red-400',    ring: 'ring-red-400',    badge: 'bg-red-100 text-red-700',     text: 'text-red-600',    label: 'CRITICAL' },
  high:     { stripe: 'bg-orange-400', border: 'border-orange-400', ring: 'ring-orange-400', badge: 'bg-orange-100 text-orange-700',text: 'text-orange-600', label: 'HIGH' },
  medium:   { stripe: 'bg-yellow-400', border: 'border-yellow-400', ring: 'ring-yellow-400', badge: 'bg-yellow-100 text-yellow-700',text: 'text-yellow-600', label: 'MEDIUM' },
  low:      { stripe: 'bg-green-400',  border: 'border-green-400',  ring: 'ring-green-400',  badge: 'bg-green-100 text-green-700',  text: 'text-green-600',  label: 'LOW' },
};
const SEV_DEFAULT = SEV['medium'];

const AGENT_STYLE: Record<string, any> = {
  blue:    { active: 'border-blue-400 bg-blue-50',     text: 'text-blue-600',    dot: 'bg-blue-500',    num: 'bg-blue-500 text-white',    line: 'border-blue-300' },
  violet:  { active: 'border-violet-400 bg-violet-50', text: 'text-violet-600',  dot: 'bg-violet-500',  num: 'bg-violet-500 text-white',  line: 'border-violet-300' },
  amber:   { active: 'border-amber-400 bg-amber-50',   text: 'text-amber-600',   dot: 'bg-amber-500',   num: 'bg-amber-500 text-white',   line: 'border-amber-300' },
  emerald: { active: 'border-emerald-400 bg-emerald-50',text: 'text-emerald-600',dot: 'bg-emerald-500', num: 'bg-emerald-500 text-white', line: 'border-emerald-300' },
  rose:    { active: 'border-rose-400 bg-rose-50',     text: 'text-rose-600',    dot: 'bg-rose-500',    num: 'bg-rose-500 text-white',    line: 'border-rose-300' },
};

@Component({
  selector: 'app-workflow-visualizer',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './workflow-visualizer.component.html',
})
export class WorkflowVisualizerComponent implements OnChanges {
  @Input() exceptions: Exception[] = [];

  agents: AgentDef[] = AGENTS;
  selectedId: number | null = null;
  isPinned = false;
  detailCache = new Map<number, any>();

  constructor(private api: ApiService) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['exceptions']) {
      this.autoFollow();
      this.checkDetailFetch();
    }
  }

  private autoFollow(): void {
    if (this.isPinned) return;
    const active = this.exceptions.filter(e => !['resolved', 'failed'].includes(e.workflow_status));
    if (!this.selectedId) {
      if (active.length)              this.selectedId = active[active.length - 1].id;
      else if (this.exceptions.length) this.selectedId = this.exceptions[this.exceptions.length - 1].id;
      return;
    }
    const current = this.exceptions.find(e => e.id === this.selectedId);
    const isDone  = !current || ['resolved', 'failed'].includes(current.workflow_status);
    if (isDone) {
      if (active.length)              this.selectedId = active[active.length - 1].id;
      else if (this.exceptions.length) this.selectedId = this.exceptions[this.exceptions.length - 1].id;
    }
  }

  private checkDetailFetch(): void {
    if (!this.selectedId) return;
    const base = this.exceptions.find(e => e.id === this.selectedId);
    if (!base) return;
    const hasOutputs = Object.values(base.agent_outputs || {}).some((o: any) => o !== null);
    if (hasOutputs || this.detailCache.has(base.id)) return;

    this.detailCache.set(base.id, 'loading');
    this.api.fetchExceptionDetail(base.id).subscribe({
      next: detail => {
        const enriched = normalizeDetail(detail);
        this.detailCache.set(base.id, {
          agent_statuses:  enriched.agent_statuses,
          agent_outputs:   enriched.agent_outputs,
          agent_durations: enriched.agent_durations,
          agent_costs:     enriched.agent_costs,
          resolution_type: enriched.resolution_type,
          location:        enriched.location,
          description:     enriched.description,
        });
      },
      error: () => this.detailCache.delete(base.id),
    });
  }

  get selected(): Exception | null {
    const base = this.exceptions.find(e => e.id === this.selectedId) ?? null;
    if (!base) return null;
    const cached = this.detailCache.get(this.selectedId!);
    if (cached && cached !== 'loading') return { ...base, ...cached };
    return base;
  }

  get isLoadingDetail(): boolean {
    return this.selectedId != null && this.detailCache.get(this.selectedId) === 'loading';
  }

  get recent(): Exception[] {
    return [...this.exceptions].slice(-12).reverse();
  }

  pin(exc: Exception): void {
    this.selectedId = exc.id;
    this.isPinned   = true;
    this.checkDetailFetch();
  }

  unpin(): void { this.isPinned = false; }

  // Severity helpers
  sev(severity: string | null): any { return SEV[severity ?? ''] ?? SEV_DEFAULT; }

  // Exception pill classes
  pillClass(exc: Exception): string {
    const sel = exc.id === this.selectedId;
    if (sel && this.isPinned) return 'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all whitespace-nowrap bg-gray-800 text-white border-gray-700';
    if (sel)                  return 'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all whitespace-nowrap bg-gray-100 text-gray-700 border-gray-300';
    return 'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all whitespace-nowrap bg-white text-gray-500 border-gray-200 hover:border-gray-300 hover:text-gray-700';
  }

  pillDotClass(exc: Exception): string {
    if (exc.workflow_status === 'failed')                             return 'w-1.5 h-1.5 rounded-full shrink-0 bg-red-400';
    if (!['resolved', 'failed'].includes(exc.workflow_status)) return `w-1.5 h-1.5 rounded-full shrink-0 ${this.sev(exc.severity).stripe} animate-pulse`;
    return 'w-1.5 h-1.5 rounded-full shrink-0 bg-green-400';
  }

  sevBadge(severity: string | null): string { return this.sev(severity).badge; }
  sevLabel(severity: string | null): string { return this.sev(severity).label.slice(0, 1); }

  // Agent step helpers
  agentStyle(color: string): any { return AGENT_STYLE[color] ?? AGENT_STYLE['blue']; }

  stepNumClass(status: string, sev: any, style: any): string {
    if (status === 'running')   return `w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-colors ${sev.stripe} text-white`;
    if (status === 'completed') return `w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-colors ${style.num}`;
    if (status === 'failed')    return 'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-colors bg-red-400 text-white';
    return 'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-colors bg-gray-200 text-gray-500';
  }

  cardClass(status: string, sev: any, style: any): string {
    if (status === 'running')   return `flex-1 rounded-xl p-3.5 mb-3 transition-all border-2 ${sev.border} bg-white ring-2 ${sev.ring} ring-opacity-30`;
    if (status === 'completed') return `flex-1 rounded-xl p-3.5 mb-3 transition-all border ${style.active}`;
    if (status === 'failed')    return 'flex-1 rounded-xl p-3.5 mb-3 transition-all border border-red-300 bg-red-50';
    return 'flex-1 rounded-xl p-3.5 mb-3 transition-all border border-gray-100 bg-gray-50';
  }

  connectorClass(status: string, style: any): string {
    return `flex-1 w-0.5 mt-1 transition-colors border-l-2 ${status === 'completed' ? style.line : 'border-dashed border-gray-200'}`;
  }

  agentLabelClass(status: string, sev: any, style: any): string {
    if (status === 'running')   return `text-xs font-bold uppercase tracking-wide ${sev.text}`;
    if (status === 'completed') return `text-xs font-bold uppercase tracking-wide ${style.text}`;
    if (status === 'failed')    return 'text-xs font-bold uppercase tracking-wide text-red-500';
    return 'text-xs font-bold uppercase tracking-wide text-gray-400';
  }

  statusLabel(status: string): string {
    if (status === 'running')   return 'processing…';
    if (status === 'completed') return 'completed';
    if (status === 'failed')    return 'failed';
    return 'waiting';
  }

  statusLabelClass(status: string, sev: any): string {
    if (status === 'running')   return `text-xs font-medium ${sev.text}`;
    if (status === 'completed') return 'text-xs font-medium text-green-600';
    if (status === 'failed')    return 'text-xs font-medium text-red-500';
    return 'text-xs font-medium text-gray-400';
  }

  // Per-step data accessors (from this.selected)
  getStatus(agentKey: string):      string                                  { return (this.selected?.agent_statuses as any)?.[agentKey] ?? 'idle'; }
  getOutput(agentKey: string):      any                                     { return (this.selected?.agent_outputs   as any)?.[agentKey] ?? null;  }
  getAgentOutput(agentKey: string): any                                     { return this.getOutput(agentKey); }
  getDuration(agentKey: string):    number | undefined                      { return (this.selected?.agent_durations as any)?.[agentKey];          }
  getCosts(agentKey: string):       { input: number; output: number } | undefined { return (this.selected?.agent_costs as any)?.[agentKey]; }

  // Formatting
  fmtMs(ms?: number): string | null {
    if (ms == null) return null;
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
  }
  fmtTokens(c?: { input: number; output: number }): string | null {
    return c ? `${(c.input + c.output).toLocaleString()}t` : null;
  }
  fmtCost(c?: { input: number; output: number }): string | null {
    return c ? `$${(c.input * 0.000003 + c.output * 0.000015).toFixed(4)}` : null;
  }
  metaLine(agentKey: string): string {
    return [this.fmtMs(this.getDuration(agentKey)), this.fmtTokens(this.getCosts(agentKey)), this.fmtCost(this.getCosts(agentKey))]
      .filter(Boolean).join(' · ');
  }

  timeAgo(iso: string): string {
    const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    return secs < 60 ? `${secs}s ago` : `${Math.floor(secs / 60)}m ago`;
  }

  isRaw(output: any): boolean { return output != null && 'reasoning' in output; }

  round(n: number): number { return Math.round(n); }

  workflowStatusClass(sel: Exception): string {
    const s = this.sev(sel.severity);
    if (sel.workflow_status === 'failed')   return 'text-xs font-medium flex items-center gap-1 text-red-500';
    if (sel.workflow_status === 'resolved') return 'text-xs font-medium flex items-center gap-1 text-green-600';
    return `text-xs font-medium flex items-center gap-1 ${s.text}`;
  }

  isActiveException(exc: Exception): boolean {
    return !['resolved', 'failed'].includes(exc.workflow_status);
  }

  urgencyColor(urgency: string): string {
    return urgency === 'immediate' ? 'text-red-600' : urgency === 'expedited' ? 'text-orange-600' : 'text-gray-500';
  }
  toneColor(tone: string): string {
    return tone === 'urgent' ? 'text-red-600' : tone === 'apologetic' ? 'text-orange-600' : 'text-blue-600';
  }
  actionStatusColor(status: string): string {
    return status === 'resolved' ? 'text-green-600' : status === 'partially_resolved' ? 'text-yellow-600' : 'text-red-500';
  }

  bounceDelay(i: number): string { return `bounce 1.2s ${i * 0.2}s infinite`; }
}
