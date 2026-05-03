import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { AGENTS, AgentStat, Exception, TotalStats } from '../models/exception.model';
import { ApiService, applyWsEvent, normalizeSummary } from './api.service';

const CIN  = 0.000003;
const COUT = 0.000015;

@Injectable({ providedIn: 'root' })
export class ExceptionStreamService implements OnDestroy {
  private _exceptions = new BehaviorSubject<Exception[]>([]);
  private _wsStatus   = new BehaviorSubject<string>('connecting');

  readonly exceptions$ = this._exceptions.asObservable();
  readonly wsStatus$   = this._wsStatus.asObservable();

  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private alive = true;

  constructor(private api: ApiService) {
    this.loadInitial();
    this.connect();
  }

  private loadInitial(): void {
    this.api.fetchExceptions(50).subscribe({
      next:  data => this._exceptions.next(data.items.map(normalizeSummary)),
      error: err  => console.warn('[api] initial load failed:', err),
    });
  }

  private connect(): void {
    if (!this.alive) return;
    this._wsStatus.next('connecting');

    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const url    = `${scheme}://${window.location.host}/api/v1/ws`;
    this.ws      = new WebSocket(url);

    this.ws.onopen = () => {
      if (!this.alive) { this.ws?.close(); return; }
      this._wsStatus.next('connected');
    };

    this.ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(ev.data as string);
        this._exceptions.next(applyWsEvent(this._exceptions.value, msg));
      } catch { /* ignore */ }
    };

    this.ws.onclose = () => {
      if (!this.alive) return;
      this._wsStatus.next('disconnected');
      this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    };

    this.ws.onerror = () => this._wsStatus.next('error');
  }

  computeStats(exceptions: Exception[]): TotalStats {
    const resolved = exceptions.filter(e => e.workflow_status === 'resolved').length;
    const failed   = exceptions.filter(e => e.workflow_status === 'failed').length;
    const active   = exceptions.filter(
      e => !['resolved', 'failed'].includes(e.workflow_status)
    ).length;

    const bySeverity:   Record<string, number> = { low: 0, medium: 0, high: 0, critical: 0 };
    const byType:       Record<string, number> = {};
    const byResolution: Record<string, number> = {};
    let totalCost = 0, totalInput = 0, totalOutput = 0;

    for (const e of exceptions) {
      if (e.severity) bySeverity[e.severity] = (bySeverity[e.severity] || 0) + 1;
      byType[e.exception_type] = (byType[e.exception_type] || 0) + 1;
      if (e.resolution_type) byResolution[e.resolution_type] = (byResolution[e.resolution_type] || 0) + 1;
      for (const c of Object.values(e.agent_costs)) {
        if (!c) continue;
        totalCost   += c.input * CIN + c.output * COUT;
        totalInput  += c.input;
        totalOutput += c.output;
      }
    }

    const agentStats: AgentStat[] = AGENTS.map(a => {
      const runs      = exceptions.filter(e => (e.agent_statuses as any)[a.key] !== 'idle').length;
      const successes = exceptions.filter(e => (e.agent_statuses as any)[a.key] === 'completed').length;
      const failures  = exceptions.filter(e => (e.agent_statuses as any)[a.key] === 'failed').length;
      const costs     = exceptions.map(e => (e.agent_costs as any)[a.key]).filter(Boolean);
      const inp  = costs.reduce((s: number, c: any) => s + c.input,  0);
      const out  = costs.reduce((s: number, c: any) => s + c.output, 0);
      return {
        ...a, runs, successes, failures,
        successRate: runs ? Math.round((successes / runs) * 100) : null,
        costUsd:     inp * CIN + out * COUT,
      };
    });

    return { resolved, failed, active, bySeverity, byType, byResolution, totalCost, totalInput, totalOutput, agentStats };
  }

  ngOnDestroy(): void {
    this.alive = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}
