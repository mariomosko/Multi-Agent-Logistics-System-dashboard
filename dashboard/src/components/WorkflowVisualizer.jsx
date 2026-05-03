import { useEffect, useRef, useState } from 'react'
import { fetchExceptionDetail, normalizeDetail } from '../lib/api'
import { AGENTS } from '../lib/mockGenerator'

// ── Severity palette ──────────────────────────────────────────────────────────

const SEV = {
  critical: {
    stripe:  'bg-red-500',
    border:  'border-red-400',
    ring:    'ring-red-400',
    badge:   'bg-red-100 text-red-700',
    text:    'text-red-600',
    label:   'CRITICAL',
  },
  high: {
    stripe:  'bg-orange-400',
    border:  'border-orange-400',
    ring:    'ring-orange-400',
    badge:   'bg-orange-100 text-orange-700',
    text:    'text-orange-600',
    label:   'HIGH',
  },
  medium: {
    stripe:  'bg-yellow-400',
    border:  'border-yellow-400',
    ring:    'ring-yellow-400',
    badge:   'bg-yellow-100 text-yellow-700',
    text:    'text-yellow-600',
    label:   'MEDIUM',
  },
  low: {
    stripe:  'bg-green-400',
    border:  'border-green-400',
    ring:    'ring-green-400',
    badge:   'bg-green-100 text-green-700',
    text:    'text-green-600',
    label:   'LOW',
  },
}

const SEV_DEFAULT = SEV.medium

// ── Agent palette ─────────────────────────────────────────────────────────────

const AGENT_STYLE = {
  blue:    { active: 'border-blue-400 bg-blue-50',    text: 'text-blue-600',    dot: 'bg-blue-500',    num: 'bg-blue-500 text-white',    line: 'border-blue-300' },
  violet:  { active: 'border-violet-400 bg-violet-50', text: 'text-violet-600',  dot: 'bg-violet-500',  num: 'bg-violet-500 text-white',  line: 'border-violet-300' },
  amber:   { active: 'border-amber-400 bg-amber-50',   text: 'text-amber-600',   dot: 'bg-amber-500',   num: 'bg-amber-500 text-white',   line: 'border-amber-300' },
  emerald: { active: 'border-emerald-400 bg-emerald-50',text: 'text-emerald-600', dot: 'bg-emerald-500', num: 'bg-emerald-500 text-white', line: 'border-emerald-300' },
  rose:    { active: 'border-rose-400 bg-rose-50',     text: 'text-rose-600',    dot: 'bg-rose-500',    num: 'bg-rose-500 text-white',    line: 'border-rose-300' },
}

// ── Small helpers ─────────────────────────────────────────────────────────────

function fmtMs(ms) {
  if (ms == null) return null
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

function fmtTokens(costs) {
  if (!costs) return null
  return `${(costs.input + costs.output).toLocaleString()}t`
}

const CIN  = 0.000003
const COUT = 0.000015
function fmtCost(costs) {
  if (!costs) return null
  const usd = costs.input * CIN + costs.output * COUT
  return `$${usd.toFixed(4)}`
}

function timeAgo(iso) {
  const secs = Math.floor((Date.now() - new Date(iso)) / 1000)
  if (secs < 60) return `${secs}s ago`
  return `${Math.floor(secs / 60)}m ago`
}

// ── Exception selector pills ──────────────────────────────────────────────────

function ExceptionPill({ exc, isSelected, isPinned, onClick }) {
  const sev     = SEV[exc.severity] ?? SEV_DEFAULT
  const isActive = !['resolved', 'failed'].includes(exc.workflow_status)
  const isFailed = exc.workflow_status === 'failed'

  return (
    <button
      onClick={onClick}
      className={`
        flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium
        border transition-all whitespace-nowrap
        ${isSelected && isPinned
          ? 'bg-gray-800 text-white border-gray-700'
          : isSelected
          ? 'bg-gray-100 text-gray-700 border-gray-300'
          : 'bg-white text-gray-500 border-gray-200 hover:border-gray-300 hover:text-gray-700'}
      `}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full shrink-0
          ${isFailed   ? 'bg-red-400'
          : isActive   ? `${sev.dot ?? 'bg-blue-400'} animate-pulse`
          : 'bg-green-400'}`}
      />
      <span className="font-mono">{exc.tracking_number.slice(-7)}</span>
      <span className={`px-1 rounded text-[10px] ${sev.badge}`}>{sev.label.slice(0,1)}</span>
    </button>
  )
}

// ── Per-agent output renderers ────────────────────────────────────────────────
// Each renderer accepts both:
//   - Structured mock/WS output  (fields like confidence, root_cause, rationale…)
//   - Raw DB record              ({ action_taken, reasoning }) — detected by 'reasoning' key
// The raw format arrives when loading historical data from REST.

function GenericOutput({ output }) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-gray-500 italic">{output.action_taken}</p>
      <p className="text-sm text-gray-700 leading-snug">{output.reasoning}</p>
    </div>
  )
}

function isRaw(output) {
  return output != null && 'reasoning' in output
}

function DetectionOutput({ output }) {
  if (!output) return null
  if (isRaw(output)) return <GenericOutput output={output} />
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-3 text-xs text-gray-500">
        <span className="font-medium text-green-600">Exception detected</span>
        <span className="text-gray-300">·</span>
        <span>{Math.round(output.confidence * 100)}% confidence</span>
      </div>
      <p className="text-sm text-gray-700 leading-snug">"{output.summary}"</p>
    </div>
  )
}

function AnalysisOutput({ output }) {
  if (!output) return null
  if (isRaw(output)) return <GenericOutput output={output} />
  const urgencyColor = output.recommended_urgency === 'immediate' ? 'text-red-600'
    : output.recommended_urgency === 'expedited' ? 'text-orange-600'
    : 'text-gray-500'
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
        {output.estimated_delay_days != null && (
          <span><span className="font-medium text-gray-700">{output.estimated_delay_days}d delay</span></span>
        )}
        <span>urgency: <span className={`font-medium ${urgencyColor}`}>{output.recommended_urgency}</span></span>
      </div>
      <p className="text-sm text-gray-700 leading-snug">{output.root_cause}</p>
    </div>
  )
}

function DecisionOutput({ output }) {
  if (!output) return null
  if (isRaw(output)) return <GenericOutput output={output} />
  const actionCount = output.action_count ?? output.actions?.length
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
        <span>resolution: <span className="font-medium text-gray-700">{output.resolution_type?.replace(/_/g, ' ')}</span></span>
        <span className={output.notify_customer ? 'text-blue-600 font-medium' : 'text-gray-400'}>
          {output.notify_customer ? '✉ notify customer' : 'no notification'}
        </span>
        {actionCount != null && (
          <span>{actionCount} action{actionCount !== 1 ? 's' : ''} planned</span>
        )}
      </div>
      <p className="text-sm text-gray-700 leading-snug">{output.rationale}</p>
    </div>
  )
}

function CommunicationOutput({ output }) {
  if (!output) return null
  if (isRaw(output)) return <GenericOutput output={output} />
  const toneColor = output.tone === 'urgent' ? 'text-red-600'
    : output.tone === 'apologetic' ? 'text-orange-600'
    : 'text-blue-600'
  // Accept both 'message' (real API) and 'message_preview' (mock)
  const preview = output.message || output.message_preview
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-3 text-xs text-gray-500">
        <span className="font-medium text-gray-700">"{output.subject}"</span>
        <span className={`font-medium ${toneColor}`}>{output.tone}</span>
      </div>
      {preview && (
        <p className="text-sm text-gray-500 italic leading-snug line-clamp-2">{preview}</p>
      )}
    </div>
  )
}

function ActionOutput({ output }) {
  if (!output) return null
  if (isRaw(output)) return <GenericOutput output={output} />
  const statusColor = output.overall_status === 'resolved' ? 'text-green-600'
    : output.overall_status === 'partially_resolved' ? 'text-yellow-600'
    : 'text-red-500'
  // Accept both 'executed_count' (mock) and 'executed_actions.length' (real API)
  const count = output.executed_count ?? output.executed_actions?.length
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-3 text-xs text-gray-500">
        {count != null && <span>{count} action{count !== 1 ? 's' : ''} executed</span>}
        <span className={`font-medium ${statusColor}`}>{output.overall_status?.replace(/_/g, ' ')}</span>
      </div>
      <p className="text-sm text-gray-700 leading-snug">{output.notes}</p>
    </div>
  )
}

const OUTPUT_RENDERERS = {
  detection:     DetectionOutput,
  analysis:      AnalysisOutput,
  decision:      DecisionOutput,
  communication: CommunicationOutput,
  action:        ActionOutput,
}

// ── Single agent step card ────────────────────────────────────────────────────

function AgentStep({ agent, stepNum, isLast, status, output, duration, costs, severity, isRunning }) {
  const style   = AGENT_STYLE[agent.color]
  const sev     = SEV[severity] ?? SEV_DEFAULT
  const Output  = OUTPUT_RENDERERS[agent.key]

  const isCompleted = status === 'completed'
  const isFailed    = status === 'failed'
  const isIdle      = status === 'idle'

  // Card border: severity-tinted when running, agent-colored when done
  const cardClass = isRunning
    ? `border-2 ${sev.border} bg-white ring-2 ${sev.ring} ring-opacity-30`
    : isCompleted
    ? `border ${style.active}`
    : isFailed
    ? 'border border-red-300 bg-red-50'
    : 'border border-gray-100 bg-gray-50'

  // Step number circle
  const numClass = isRunning
    ? `${sev.stripe} text-white`
    : isCompleted
    ? `${style.num}`
    : isFailed
    ? 'bg-red-400 text-white'
    : 'bg-gray-200 text-gray-500'

  return (
    <div className="flex gap-3">
      {/* Left: step number + connector line */}
      <div className="flex flex-col items-center shrink-0" style={{ width: 28 }}>
        <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-colors ${numClass}`}>
          {isCompleted ? '✓' : isFailed ? '✗' : stepNum}
        </div>
        {!isLast && (
          <div className={`flex-1 w-0.5 mt-1 transition-colors ${
            isCompleted ? `border-l-2 ${style.line}` : 'border-l-2 border-dashed border-gray-200'
          }`} style={{ minHeight: 16 }} />
        )}
      </div>

      {/* Right: agent card */}
      <div className={`flex-1 rounded-xl p-3.5 mb-3 transition-all ${cardClass}`}>
        {/* Card header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {isRunning && (
              <span className={`w-2 h-2 rounded-full animate-pulse ${sev.stripe}`} />
            )}
            <span className={`text-xs font-bold uppercase tracking-wide ${
              isRunning ? sev.text : isCompleted ? style.text : isFailed ? 'text-red-500' : 'text-gray-400'
            }`}>
              {agent.label}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Timing + token meta */}
            {(duration || costs) && (
              <span className="text-xs text-gray-400 tabular-nums">
                {[fmtMs(duration), fmtTokens(costs), fmtCost(costs)]
                  .filter(Boolean).join(' · ')}
              </span>
            )}
            {/* Status badge */}
            <span className={`text-xs font-medium ${
              isRunning ? sev.text
              : isCompleted ? 'text-green-600'
              : isFailed ? 'text-red-500'
              : 'text-gray-400'
            }`}>
              {isRunning ? 'processing…' : isCompleted ? 'completed' : isFailed ? 'failed' : 'waiting'}
            </span>
          </div>
        </div>

        {/* Output content */}
        {isRunning && !output && (
          <div className="flex items-center gap-2 mt-1">
            <div className="flex gap-0.5">
              {[0, 1, 2].map(i => (
                <span
                  key={i}
                  className={`w-1.5 h-1.5 rounded-full ${sev.stripe} opacity-70`}
                  style={{ animation: `bounce 1.2s ${i * 0.2}s infinite` }}
                />
              ))}
            </div>
            <span className="text-xs text-gray-400">Calling Claude API…</span>
          </div>
        )}

        {isCompleted && output && <Output output={output} />}

        {isFailed && (
          <p className="text-xs text-red-500 mt-1">
            Agent failed — pipeline halted at this step.
          </p>
        )}

        {isIdle && (
          <p className="text-xs text-gray-400 mt-0.5">Waiting for upstream agent…</p>
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function WorkflowVisualizer({ exceptions }) {
  const [selectedId,  setSelectedId]  = useState(null)
  const [isPinned,    setIsPinned]    = useState(false)
  // Cache enriched detail for real exceptions: id → enriched fields | 'loading'
  const [detailCache, setDetailCache] = useState({})

  // Auto-follow: switch only when the tracked exception finishes
  useEffect(() => {
    if (isPinned) return

    const active = exceptions.filter(
      e => !['resolved', 'failed'].includes(e.workflow_status)
    )

    if (!selectedId) {
      if (active.length > 0) setSelectedId(active[active.length - 1].id)
      else if (exceptions.length > 0) setSelectedId(exceptions[exceptions.length - 1].id)
      return
    }

    const current = exceptions.find(e => e.id === selectedId)
    const isDone  = !current || ['resolved', 'failed'].includes(current.workflow_status)

    if (isDone) {
      if (active.length > 0) setSelectedId(active[active.length - 1].id)
      else if (exceptions.length > 0) setSelectedId(exceptions[exceptions.length - 1].id)
    }
  }, [exceptions, isPinned, selectedId])

  // On-demand detail fetch: when a real exception is selected and has no agent
  // outputs yet (REST list view only includes summary fields), fetch the full
  // detail endpoint to populate agent outputs for historical display.
  const baseSelected = exceptions.find(e => e.id === selectedId) ?? null
  useEffect(() => {
    if (!baseSelected) return
    if (baseSelected.source !== 'real') return
    const hasOutputs = Object.values(baseSelected.agent_outputs || {}).some(o => o !== null)
    if (hasOutputs) return
    if (detailCache[baseSelected.id]) return  // already loading or loaded

    setDetailCache(prev => ({ ...prev, [baseSelected.id]: 'loading' }))
    fetchExceptionDetail(baseSelected.id)
      .then(detail => {
        const enriched = normalizeDetail(detail)
        setDetailCache(prev => ({
          ...prev,
          [baseSelected.id]: {
            agent_statuses:  enriched.agent_statuses,
            agent_outputs:   enriched.agent_outputs,
            agent_durations: enriched.agent_durations,
            agent_costs:     enriched.agent_costs,
            resolution_type: enriched.resolution_type,
            location:        enriched.location,
            description:     enriched.description,
          },
        }))
      })
      .catch(() => setDetailCache(prev => ({ ...prev, [baseSelected.id]: null })))
  }, [baseSelected, detailCache])

  // Merge cached detail into the base record for display
  const cached   = detailCache[selectedId]
  const selected = baseSelected
    ? (cached && cached !== 'loading' ? { ...baseSelected, ...cached } : baseSelected)
    : null
  const isLoadingDetail = cached === 'loading'

  const sev      = selected ? (SEV[selected.severity] ?? SEV_DEFAULT) : SEV_DEFAULT
  const isActive = selected && !['resolved', 'failed'].includes(selected.workflow_status)
  const isFailed = selected?.workflow_status === 'failed'

  // Recent 12 exceptions for the selector strip
  const recent = [...exceptions].slice(-12).reverse()

  function pin(exc) {
    setSelectedId(exc.id)
    setIsPinned(true)
  }

  function unpin() {
    setIsPinned(false)
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
          Workflow Detail
        </h2>
        <div className="flex items-center gap-2">
          {isPinned ? (
            <button
              onClick={unpin}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-md px-2 py-0.5 hover:bg-gray-50"
            >
              <span>📌</span>
              <span>Pinned</span>
              <span className="text-gray-400 hover:text-gray-600">×</span>
            </button>
          ) : (
            <span className="text-xs text-blue-500 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              Auto-following
            </span>
          )}
        </div>
      </div>

      {/* Exception selector strip */}
      {recent.length > 0 && (
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {recent.map(exc => (
            <ExceptionPill
              key={exc.id}
              exc={exc}
              isSelected={exc.id === selectedId}
              isPinned={isPinned}
              onClick={() => pin(exc)}
            />
          ))}
        </div>
      )}

      {/* Main panel */}
      {!selected ? (
        <div className="py-12 text-center text-sm text-gray-400">
          Waiting for exceptions…
        </div>
      ) : (
        <div>
          {/* Exception header */}
          <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border-2 mb-4 ${sev.border} bg-white`}>
            {/* Severity stripe */}
            <div className={`w-1 self-stretch rounded-full ${sev.stripe}`} />

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-xs font-bold px-2 py-0.5 rounded ${sev.badge}`}>
                  {sev.label}
                </span>
                <span className="font-mono text-sm text-gray-700 font-semibold">
                  {selected.tracking_number}
                </span>
                <span className="text-gray-300">·</span>
                <span className="text-sm text-gray-500">{selected.carrier}</span>
                <span className="text-gray-300">·</span>
                <span className="text-sm text-gray-600">{selected.exception_type.replace(/_/g, ' ')}</span>
                {selected.location && (
                  <>
                    <span className="text-gray-300">·</span>
                    <span className="text-xs text-gray-400">{selected.location}</span>
                  </>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <span className={`text-xs font-medium flex items-center gap-1 ${
                isFailed ? 'text-red-500'
                : selected.workflow_status === 'resolved' ? 'text-green-600'
                : sev.text
              }`}>
                {isActive && <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${sev.stripe}`} />}
                {selected.workflow_status.replace(/_/g, ' ')}
              </span>
              <span className="text-xs text-gray-400">{timeAgo(selected.detected_at)}</span>
            </div>
          </div>

          {/* Agent pipeline */}
          {isLoadingDetail ? (
            <div className="space-y-2 py-2">
              {AGENTS.map(agent => (
                <div key={agent.key} className="flex items-center gap-3 px-3 py-3 rounded-lg border border-gray-100 animate-pulse">
                  <div className="w-5 h-5 rounded-full bg-gray-200 shrink-0" />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-3 bg-gray-200 rounded w-24" />
                    <div className="h-2.5 bg-gray-100 rounded w-48" />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div>
              {AGENTS.map((agent, i) => {
                const status   = selected.agent_statuses[agent.key]
                const isRunning = status === 'running'
                return (
                  <AgentStep
                    key={agent.key}
                    agent={agent}
                    stepNum={i + 1}
                    isLast={i === AGENTS.length - 1}
                    status={status}
                    output={selected.agent_outputs[agent.key]}
                    duration={selected.agent_durations[agent.key]}
                    costs={selected.agent_costs[agent.key]}
                    severity={selected.severity}
                    isRunning={isRunning}
                  />
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Bounce keyframes */}
      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: scaleY(0.6); opacity: 0.5; }
          40%            { transform: scaleY(1.0); opacity: 1; }
        }
      `}</style>
    </div>
  )
}
