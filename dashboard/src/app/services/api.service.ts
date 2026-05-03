import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { AgentKey, AgentStatus, Exception } from '../models/exception.model';

const PIPELINE: AgentKey[] = ['detection', 'analysis', 'decision', 'communication', 'action'];

const AGENT_KEY: Record<string, AgentKey> = {
  detection_agent:     'detection',
  analysis_agent:      'analysis',
  decision_agent:      'decision',
  communication_agent: 'communication',
  action_agent:        'action',
};

const WORKFLOW_TO_RUNNING: Record<string, AgentKey> = {
  detecting:     'detection',
  analyzing:     'analysis',
  deciding:      'decision',
  communicating: 'communication',
  acting:        'action',
};

export function normalizeSummary(item: any): Exception {
  const runningAgent = WORKFLOW_TO_RUNNING[item.workflow_status];
  const runningIdx   = runningAgent ? PIPELINE.indexOf(runningAgent) : -1;

  const agent_statuses = Object.fromEntries(PIPELINE.map((a, i) => [
    a,
    item.workflow_status === 'resolved' ? 'completed'
    : item.workflow_status === 'failed'
      ? (i < runningIdx ? 'completed' : i === runningIdx ? 'failed' : 'idle')
    : i < runningIdx ? 'completed'
    : i === runningIdx ? 'running'
    : 'idle',
  ])) as Record<AgentKey, AgentStatus>;

  return {
    ...item,
    source:          'real',
    agent_statuses,
    agent_outputs:   Object.fromEntries(PIPELINE.map(a => [a, null])) as Record<AgentKey, any>,
    agent_durations: {},
    agent_costs:     {},
    resolution_type: null,
    location:        null,
  };
}

export function normalizeDetail(detail: any): Exception {
  const agent_statuses  = Object.fromEntries(PIPELINE.map(a => [a, 'idle'])) as Record<AgentKey, AgentStatus>;
  const agent_outputs   = Object.fromEntries(PIPELINE.map(a => [a, null])) as Record<AgentKey, any>;
  const agent_durations: Partial<Record<AgentKey, number>> = {};
  const agent_costs:     Partial<Record<AgentKey, { input: number; output: number }>> = {};

  for (const action of (detail.agent_actions || [])) {
    const key = AGENT_KEY[action.agent_name];
    if (!key) continue;
    agent_statuses[key] = action.status === 'completed' ? 'completed'
                        : action.status === 'failed'    ? 'failed'
                        : 'idle';
    agent_outputs[key] = { action_taken: action.action_taken, reasoning: action.reasoning };
    if (action.duration_ms)  agent_durations[key] = action.duration_ms;
    if (action.input_tokens) agent_costs[key] = {
      input:  action.input_tokens,
      output: action.output_tokens ?? 0,
    };
  }

  return {
    ...normalizeSummary(detail),
    agent_statuses,
    agent_outputs,
    agent_durations,
    agent_costs,
    resolution_type: detail.resolution?.resolution_type ?? null,
    location:        detail.raw_event?.location ?? null,
    description:     detail.description,
  };
}

export function applyWsEvent(exceptions: Exception[], msg: any): Exception[] {
  switch (msg.event) {
    case 'exception.created': {
      if (exceptions.some(e => e.id === msg.exception_id)) return exceptions;
      const newExc: Exception = {
        id:              msg.exception_id,
        tracking_number: msg.tracking_number,
        carrier:         msg.carrier,
        customer_name:   msg.customer_name,
        exception_type:  msg.exception_type,
        severity:        msg.severity,
        workflow_status: msg.workflow_status,
        detected_at:     msg.detected_at,
        shipment_id:     msg.shipment_id,
        source:          'real',
        location:        msg.location,
        agent_statuses:  Object.fromEntries(PIPELINE.map(a => [a, 'idle'])) as Record<AgentKey, AgentStatus>,
        agent_outputs:   Object.fromEntries(PIPELINE.map(a => [a, null])) as Record<AgentKey, any>,
        agent_durations: {},
        agent_costs:     {},
        resolution_type: null,
      };
      return [...exceptions, newExc].slice(-200);
    }

    case 'agent.started': {
      const key = AGENT_KEY[msg.agent_name];
      return exceptions.map(e => e.id !== msg.exception_id ? e : {
        ...e,
        workflow_status: msg.workflow_status,
        agent_statuses: { ...e.agent_statuses, ...(key ? { [key]: 'running' as AgentStatus } : {}) },
      });
    }

    case 'agent.completed': {
      const key = AGENT_KEY[msg.agent_name];
      return exceptions.map(e => e.id !== msg.exception_id ? e : {
        ...e,
        workflow_status: msg.workflow_status,
        severity:        msg.severity ?? e.severity,
        agent_statuses:  { ...e.agent_statuses, ...(key ? { [key]: 'completed' as AgentStatus } : {}) },
        agent_outputs:   { ...e.agent_outputs,  ...(key && msg.output ? { [key]: msg.output } : {}) },
        agent_durations: { ...e.agent_durations, ...(key && msg.duration_ms ? { [key]: msg.duration_ms } : {}) },
        agent_costs:     {
          ...e.agent_costs,
          ...(key && msg.input_tokens ? { [key]: { input: msg.input_tokens, output: msg.output_tokens ?? 0 } } : {}),
        },
      });
    }

    case 'agent.failed': {
      const key = AGENT_KEY[msg.agent_name];
      return exceptions.map(e => e.id !== msg.exception_id ? e : {
        ...e,
        workflow_status: 'failed',
        agent_statuses:  { ...e.agent_statuses, ...(key ? { [key]: 'failed' as AgentStatus } : {}) },
      });
    }

    case 'pipeline.resolved':
      return exceptions.map(e => e.id !== msg.exception_id ? e : {
        ...e,
        workflow_status: 'resolved',
        resolution_type: msg.resolution_type ?? e.resolution_type,
      });

    case 'pipeline.failed':
      return exceptions.map(e => e.id !== msg.exception_id ? e : {
        ...e, workflow_status: 'failed',
      });

    default:
      return exceptions;
  }
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private http: HttpClient) {}

  fetchExceptions(pageSize = 50): Observable<{ items: any[] }> {
    return this.http.get<{ items: any[] }>(`/api/v1/monitoring/exceptions?page_size=${pageSize}&page=1`);
  }

  fetchExceptionDetail(id: number): Observable<any> {
    return this.http.get<any>(`/api/v1/monitoring/exceptions/${id}`);
  }

  triggerSimulation(scenario: string | null): Observable<any> {
    return this.http.post<any>('/api/v1/simulate/exception', { scenario });
  }
}
