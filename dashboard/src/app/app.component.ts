import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subject, takeUntil } from 'rxjs';
import { ExceptionStreamService } from './services/exception-stream.service';
import { ApiService } from './services/api.service';
import { AgentPipelineComponent } from './components/agent-pipeline/agent-pipeline.component';
import { WorkflowVisualizerComponent } from './components/workflow-visualizer/workflow-visualizer.component';
import { LiveEventStreamComponent } from './components/live-event-stream/live-event-stream.component';
import { ResolutionMetricsComponent } from './components/resolution-metrics/resolution-metrics.component';
import { CostTrackerComponent } from './components/cost-tracker/cost-tracker.component';
import { Exception, TotalStats } from './models/exception.model';

const SCENARIO_ICONS: Record<string, string> = {
  delay:          '🌩️',
  lost:           '🔍',
  damaged:        '📦',
  address_issue:  '📍',
  customs_hold:   '🛃',
  failed_delivery:'🚚',
};

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    AgentPipelineComponent,
    WorkflowVisualizerComponent,
    LiveEventStreamComponent,
    ResolutionMetricsComponent,
    CostTrackerComponent,
  ],
  templateUrl: './app.component.html',
})
export class AppComponent implements OnInit, OnDestroy {
  exceptions: Exception[] = [];
  wsStatus = 'connecting';
  stats: TotalStats = this.emptyStats();
  activeCount = 0;

  simulating    = false;
  lastScenario: string | null = null;
  simError:     string | null = null;

  scenarios = Object.entries(SCENARIO_ICONS).map(([key, icon]) => ({
    key, icon, label: key.replace(/_/g, ' '),
  }));

  private destroy$ = new Subject<void>();

  constructor(
    private stream: ExceptionStreamService,
    private api:    ApiService,
  ) {}

  ngOnInit(): void {
    this.stream.exceptions$.pipe(takeUntil(this.destroy$)).subscribe(excs => {
      this.exceptions   = excs;
      this.stats        = this.stream.computeStats(excs);
      this.activeCount  = excs.filter(e => !['resolved', 'failed'].includes(e.workflow_status)).length;
    });
    this.stream.wsStatus$.pipe(takeUntil(this.destroy$)).subscribe(s => {
      this.wsStatus = s;
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  wsStatusClass(): string {
    const map: Record<string, string> = {
      connected:    'bg-green-400',
      connecting:   'bg-yellow-400 animate-pulse',
      disconnected: 'bg-red-400',
      error:        'bg-red-400',
    };
    return map[this.wsStatus] ?? 'bg-gray-300';
  }

  handleSimulate(scenario: string | null): void {
    if (this.simulating || this.wsStatus !== 'connected') return;
    this.simulating   = true;
    this.simError     = null;
    this.lastScenario = scenario;
    this.api.triggerSimulation(scenario).subscribe({
      next:  () => { this.simulating = false; },
      error: (err: any) => { this.simError = err.message ?? 'Unknown error'; this.simulating = false; },
    });
  }

  onScenarioChange(event: Event): void {
    const val = (event.target as HTMLSelectElement).value;
    if (val) {
      this.handleSimulate(val);
      (event.target as HTMLSelectElement).value = '';
    }
  }

  scenarioIcon(key: string): string {
    return SCENARIO_ICONS[key] ?? '';
  }

  private emptyStats(): TotalStats {
    return {
      resolved: 0, failed: 0, active: 0,
      bySeverity: {}, byType: {}, byResolution: {},
      totalCost: 0, totalInput: 0, totalOutput: 0,
      agentStats: [],
    };
  }
}
