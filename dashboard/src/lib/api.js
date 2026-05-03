// REST client for the FastAPI backend.
// All paths are relative so the Vite proxy (/api → localhost:8000) handles routing.

const PIPELINE = ['detection', 'analysis', 'decision', 'communication', 'action']

const AGENT_KEY = {
  detection_agent:     'detection',
  analysis_agent:      'analysis',
  decision_agent:      'decision',
  communication_agent: 'communication',
  action_agent:        'action',
}

const WORKFLOW_TO_RUNNING = {
  detecting:     'detection',
  analyzing:     'analysis',
  deciding:      'decision',
  communicating: 'communication',
  acting:        'action',
}

// ── Normalization ─────────────────────────────────────────────────────────────

/**
 * Convert an ExceptionSummary (list endpoint) to the shape the React
 * components expect.  agent_outputs will be null until WS events arrive
 * or a detail fetch enriches the record.
 */
export function normalizeSummary(item) {
  const runningAgent = WORKFLOW_TO_RUNNING[item.workflow_status]
  const runningIdx   = runningAgent ? PIPELINE.indexOf(runningAgent) : -1

  const agent_statuses = Object.fromEntries(PIPELINE.map((a, i) => [
    a,
    item.workflow_status === 'resolved' ? 'completed'
    : item.workflow_status === 'failed'
      ? (i < runningIdx ? 'completed' : i === runningIdx ? 'failed' : 'idle')
    : i < runningIdx ? 'completed'
    : i === runningIdx ? 'running'
    : 'idle',
  ]))

  return {
    ...item,
    source: 'real',
    agent_statuses,
    agent_outputs:  Object.fromEntries(PIPELINE.map(a => [a, null])),
    agent_durations: {},
    agent_costs:    {},
    resolution_type: null,
    location: null,
  }
}

/**
 * Convert a detail endpoint response (with agent_actions[]) to enrich an
 * existing record with real agent outputs and timing.
 */
export function normalizeDetail(detail) {
  const agent_statuses  = Object.fromEntries(PIPELINE.map(a => [a, 'idle']))
  const agent_outputs   = Object.fromEntries(PIPELINE.map(a => [a, null]))
  const agent_durations = {}
  const agent_costs     = {}

  for (const action of (detail.agent_actions || [])) {
    const key = AGENT_KEY[action.agent_name]
    if (!key) continue
    agent_statuses[key] = action.status === 'completed' ? 'completed'
                        : action.status === 'failed'    ? 'failed'
                        : 'idle'
    // Store as a "raw record" shape — WorkflowVisualizer detects this and
    // falls back to the generic renderer.
    agent_outputs[key] = {
      action_taken: action.action_taken,
      reasoning:    action.reasoning,
    }
    if (action.duration_ms)   agent_durations[key] = action.duration_ms
    if (action.input_tokens)  agent_costs[key] = {
      input:  action.input_tokens,
      output: action.output_tokens ?? 0,
    }
  }

  return {
    ...normalizeSummary(detail),
    agent_statuses,
    agent_outputs,
    agent_durations,
    agent_costs,
    resolution_type: detail.resolution?.resolution_type ?? null,
    location: detail.raw_event?.location ?? null,
    description: detail.description,
  }
}

// ── WS event → state updaters ─────────────────────────────────────────────────

export function applyWsEvent(exceptions, msg) {
  switch (msg.event) {

    case 'exception.created': {
      if (exceptions.some(e => e.id === msg.exception_id)) return exceptions
      const newExc = {
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
        agent_statuses:  Object.fromEntries(PIPELINE.map(a => [a, 'idle'])),
        agent_outputs:   Object.fromEntries(PIPELINE.map(a => [a, null])),
        agent_durations: {},
        agent_costs:     {},
        resolution_type: null,
      }
      return [...exceptions, newExc].slice(-200)
    }

    case 'agent.started': {
      const key = AGENT_KEY[msg.agent_name]
      return exceptions.map(e => e.id !== msg.exception_id ? e : {
        ...e,
        workflow_status: msg.workflow_status,
        agent_statuses: { ...e.agent_statuses, ...(key ? { [key]: 'running' } : {}) },
      })
    }

    case 'agent.completed': {
      const key = AGENT_KEY[msg.agent_name]
      return exceptions.map(e => e.id !== msg.exception_id ? e : {
        ...e,
        workflow_status: msg.workflow_status,
        severity:        msg.severity ?? e.severity,
        agent_statuses:  { ...e.agent_statuses, ...(key ? { [key]: 'completed' } : {}) },
        agent_outputs:   { ...e.agent_outputs,  ...(key && msg.output ? { [key]: msg.output } : {}) },
        agent_durations: { ...e.agent_durations, ...(key && msg.duration_ms ? { [key]: msg.duration_ms } : {}) },
        agent_costs:     {
          ...e.agent_costs,
          ...(key && msg.input_tokens ? { [key]: { input: msg.input_tokens, output: msg.output_tokens ?? 0 } } : {}),
        },
      })
    }

    case 'agent.failed': {
      const key = AGENT_KEY[msg.agent_name]
      return exceptions.map(e => e.id !== msg.exception_id ? e : {
        ...e,
        workflow_status: 'failed',
        agent_statuses:  { ...e.agent_statuses, ...(key ? { [key]: 'failed' } : {}) },
      })
    }

    case 'pipeline.resolved':
      return exceptions.map(e => e.id !== msg.exception_id ? e : {
        ...e,
        workflow_status: 'resolved',
        resolution_type: msg.resolution_type ?? e.resolution_type,
      })

    case 'pipeline.failed':
      return exceptions.map(e => e.id !== msg.exception_id ? e : {
        ...e,
        workflow_status: 'failed',
      })

    default:
      return exceptions
  }
}

// ── Fetch helpers ─────────────────────────────────────────────────────────────

async function apiFetch(path, options) {
  const res = await fetch(path, options)
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  return res.json()
}

export const fetchExceptions = (pageSize = 50) =>
  apiFetch(`/api/v1/monitoring/exceptions?page_size=${pageSize}&page=1`)

export const fetchExceptionDetail = (id) =>
  apiFetch(`/api/v1/monitoring/exceptions/${id}`)

export const fetchScenarios = () =>
  apiFetch('/api/v1/simulate/scenarios')

export const triggerSimulation = (scenario) =>
  apiFetch('/api/v1/simulate/exception', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ scenario }),
  })
