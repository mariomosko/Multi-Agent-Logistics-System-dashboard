import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TotalStats } from '../../models/exception.model';

const TYPE_LABELS: Record<string, string> = {
  delay: 'Delay', lost: 'Lost', damaged: 'Damaged',
  address_issue: 'Address Issue', customs_hold: 'Customs Hold', failed_delivery: 'Failed Delivery',
};

const RESOLUTION_LABELS: Record<string, string> = {
  reroute: 'Reroute', reship: 'Reship', refund: 'Refund',
  contact_carrier: 'Contact Carrier', schedule_redelivery: 'Redeliver',
  monitor: 'Monitor', escalate: 'Escalate',
};

@Component({
  selector: 'app-resolution-metrics',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './resolution-metrics.component.html',
})
export class ResolutionMetricsComponent {
  @Input() stats!: TotalStats;

  get resolved(): number { return this.stats?.resolved ?? 0; }
  get failed():   number { return this.stats?.failed   ?? 0; }
  get active():   number { return this.stats?.active   ?? 0; }
  get total():    number { return this.resolved + this.failed + this.active; }

  get resolvedPct(): number { return this.total ? (this.resolved / this.total) * 100 : 0; }
  get failedPct():   number { return this.total ? (this.failed   / this.total) * 100 : 0; }
  get activePct():   number { return this.total ? (this.active   / this.total) * 100 : 0; }

  get typeEntries(): [string, number][] {
    return Object.entries(this.stats?.byType ?? {}).sort((a, b) => b[1] - a[1]);
  }
  get typeMax(): number { return Math.max(...Object.values(this.stats?.byType ?? {}), 1); }

  get resEntries(): [string, number][] {
    return Object.entries(this.stats?.byResolution ?? {}).sort((a, b) => b[1] - a[1]);
  }
  get resMax(): number { return Math.max(...this.resEntries.map(e => e[1]), 1); }

  successRateDisplay(): string {
    if (this.total === 0) return '—';
    return `${Math.round((this.resolved / (this.resolved + this.failed || 1)) * 100)}%`;
  }

  successRateClass(): string {
    if (this.total === 0) return 'text-lg font-bold text-gray-400';
    const rate = this.resolved / (this.resolved + this.failed || 1);
    const color = rate >= 0.9 ? 'text-green-600' : rate >= 0.7 ? 'text-yellow-600' : 'text-red-500';
    return `text-lg font-bold ${color}`;
  }

  barPct(value: number, max: number): number {
    return max > 0 ? Math.round((value / max) * 100) : 0;
  }

  typeLabel(key: string):  string { return TYPE_LABELS[key]       || key; }
  resLabel(key: string):   string { return RESOLUTION_LABELS[key] || key; }
  sevValue(key: string):   number { return this.stats?.bySeverity?.[key] ?? 0; }

  severityRows = [
    { key: 'critical', color: 'bg-red-400' },
    { key: 'high',     color: 'bg-orange-400' },
    { key: 'medium',   color: 'bg-yellow-400' },
    { key: 'low',      color: 'bg-green-400' },
  ];
}
