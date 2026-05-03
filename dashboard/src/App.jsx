import { useState } from 'react'
import AgentPipeline from './components/AgentPipeline'
import CostTracker from './components/CostTracker'
import LiveEventStream from './components/LiveEventStream'
import ResolutionMetrics from './components/ResolutionMetrics'
import WorkflowVisualizer from './components/WorkflowVisualizer'
import { useExceptionStream } from './hooks/useExceptionStream'
import { fetchScenarios, triggerSimulation } from './lib/api'
import { totalStats } from './lib/mockGenerator'

const WS_STATUS_STYLES = {
  connected:    'bg-green-400',
  connecting:   'bg-yellow-400 animate-pulse',
  disconnected: 'bg-red-400',
  error:        'bg-red-400',
}

const SCENARIO_ICONS = {
  delay:          '🌩️',
  lost:           '🔍',
  damaged:        '📦',
  address_issue:  '📍',
  customs_hold:   '🛃',
  failed_delivery:'🚚',
}

export default function App() {
  const { exceptions, wsStatus } = useExceptionStream()
  const [simulating,  setSimulating]  = useState(false)
  const [lastScenario, setLastScenario] = useState(null)
  const [simError,    setSimError]    = useState(null)

  // Aggregate stats — same computation works for both real + mock shapes
  const byResolution = {}
  for (const e of exceptions) {
    if (e.resolution_type) {
      byResolution[e.resolution_type] = (byResolution[e.resolution_type] || 0) + 1
    }
  }
  const stats = { ...totalStats(exceptions), byResolution }

  const activeCount = exceptions.filter(
    e => !['resolved', 'failed'].includes(e.workflow_status)
  ).length

  async function handleSimulate(scenario) {
    setSimulating(true)
    setSimError(null)
    setLastScenario(scenario ?? null)
    try {
      await triggerSimulation(scenario ?? null)
    } catch (err) {
      setSimError(err.message)
    } finally {
      setSimulating(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 text-gray-800">
      {/* ── Header ───────────────────────────────────────────────────────────── */}
      <header className="bg-white border-b border-gray-200 px-5 py-2.5 flex items-center justify-between sticky top-0 z-10 gap-4">
        {/* Left: logo + WS status */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className={`w-2 h-2 rounded-full ${WS_STATUS_STYLES[wsStatus] ?? 'bg-gray-300'}`} />
          <h1 className="text-sm font-bold text-gray-800 tracking-tight">
            Logistics Exception Dashboard
          </h1>
          <span className="text-xs text-gray-400 hidden sm:inline">
            {wsStatus === 'connected'    && '● live'}
            {wsStatus === 'connecting'   && '⟳ connecting…'}
            {wsStatus === 'disconnected' && '○ reconnecting…'}
          </span>
        </div>

        {/* Middle: simulate controls */}
        <div className="flex items-center gap-2 flex-wrap justify-center">
          {/* Quick-fire random scenario */}
          <button
            onClick={() => handleSimulate(null)}
            disabled={simulating || wsStatus !== 'connected'}
            className={`
              text-xs px-3 py-1.5 rounded-md font-medium transition-colors
              flex items-center gap-1.5
              ${simulating || wsStatus !== 'connected'
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-indigo-600 text-white hover:bg-indigo-700'}
            `}
          >
            {simulating ? '⟳ Running…' : '⚡ Simulate Exception'}
          </button>

          {/* Scenario picker */}
          <select
            className="text-xs border border-gray-200 rounded-md px-2 py-1.5 text-gray-600 bg-white hover:border-gray-300 focus:outline-none disabled:opacity-50"
            defaultValue=""
            disabled={simulating || wsStatus !== 'connected'}
            onChange={e => { if (e.target.value) handleSimulate(e.target.value); e.target.value = '' }}
          >
            <option value="" disabled>Pick scenario…</option>
            {Object.entries(SCENARIO_ICONS).map(([key, icon]) => (
              <option key={key} value={key}>{icon} {key.replace('_', ' ')}</option>
            ))}
          </select>

          {/* Last triggered indicator */}
          {lastScenario && !simulating && (
            <span className="text-xs text-gray-400">
              last: {SCENARIO_ICONS[lastScenario]} {lastScenario}
            </span>
          )}
          {simError && (
            <span className="text-xs text-red-500 max-w-xs truncate" title={simError}>
              ⚠ {simError}
            </span>
          )}
        </div>

        {/* Right: counters */}
        <div className="flex items-center gap-3 shrink-0">
          {activeCount > 0 && (
            <span className="text-xs text-blue-500 font-medium">
              {activeCount} active
            </span>
          )}
          <span className="text-xs text-gray-400">{exceptions.length} total</span>
        </div>
      </header>

      <main className="p-4 space-y-4 max-w-screen-xl mx-auto">
        {/* ── Agent summary row ───────────────────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <AgentPipeline exceptions={exceptions} agentStats={stats.agentStats} />
        </div>

        {/* ── Workflow detail + live stream ────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div
            className="lg:col-span-2 bg-white rounded-xl border border-gray-200 p-4 overflow-y-auto"
            style={{ maxHeight: 640 }}
          >
            <WorkflowVisualizer exceptions={exceptions} />
          </div>
          <div
            className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col"
            style={{ maxHeight: 640 }}
          >
            <LiveEventStream exceptions={exceptions} />
          </div>
        </div>

        {/* ── Metrics row ─────────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <ResolutionMetrics stats={stats} />
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <CostTracker stats={stats} />
          </div>
        </div>
      </main>
    </div>
  )
}
