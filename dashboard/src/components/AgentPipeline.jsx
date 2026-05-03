import { AGENTS } from '../lib/mockGenerator'

const AGENT_COLORS = {
  blue:    { ring: 'ring-blue-400',    bg: 'bg-blue-50',    text: 'text-blue-600',    dot: 'bg-blue-400' },
  violet:  { ring: 'ring-violet-400',  bg: 'bg-violet-50',  text: 'text-violet-600',  dot: 'bg-violet-400' },
  amber:   { ring: 'ring-amber-400',   bg: 'bg-amber-50',   text: 'text-amber-600',   dot: 'bg-amber-400' },
  emerald: { ring: 'ring-emerald-400', bg: 'bg-emerald-50', text: 'text-emerald-600', dot: 'bg-emerald-400' },
  rose:    { ring: 'ring-rose-400',    bg: 'bg-rose-50',    text: 'text-rose-600',    dot: 'bg-rose-400' },
}

function statusLabel(status) {
  if (status === 'running')   return { label: 'Processing', pulse: true,  class: 'text-blue-500' }
  if (status === 'completed') return { label: 'Done',       pulse: false, class: 'text-green-600' }
  if (status === 'failed')    return { label: 'Failed',     pulse: false, class: 'text-red-500' }
  return                             { label: 'Idle',       pulse: false, class: 'text-gray-400' }
}

export default function AgentPipeline({ exceptions, agentStats }) {
  // Count how many exceptions each agent is currently running
  const runningCounts = Object.fromEntries(
    AGENTS.map(a => [
      a.key,
      exceptions.filter(e => e.agent_statuses[a.key] === 'running').length,
    ])
  )

  return (
    <div>
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-4">
        Agent Pipeline
      </h2>

      <div className="flex items-stretch gap-0">
        {AGENTS.map((agent, i) => {
          const c      = AGENT_COLORS[agent.color]
          const stat   = agentStats?.find(s => s.key === agent.key)
          const active = runningCounts[agent.key] > 0

          return (
            <div key={agent.key} className="flex items-center flex-1 min-w-0">
              {/* Agent card */}
              <div className={`flex-1 rounded-xl border-2 p-3 transition-all ${active ? `${c.ring} ${c.bg} ring-2` : 'border-gray-100 bg-white'}`}>
                <div className="flex items-center gap-2 mb-2">
                  <span className={`w-2 h-2 rounded-full ${active ? `${c.dot} animate-pulse` : 'bg-gray-200'}`} />
                  <span className={`text-xs font-semibold ${active ? c.text : 'text-gray-500'}`}>
                    {agent.label}
                  </span>
                </div>

                {active && (
                  <div className={`text-xs font-medium mb-2 ${c.text}`}>
                    {runningCounts[agent.key]} active
                  </div>
                )}

                <div className="space-y-1 text-xs text-gray-500">
                  <div className="flex justify-between">
                    <span>Runs</span>
                    <span className="font-medium text-gray-700">{stat?.runs ?? 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Success</span>
                    <span className={`font-medium ${stat?.successRate >= 90 ? 'text-green-600' : stat?.successRate >= 70 ? 'text-yellow-600' : 'text-red-500'}`}>
                      {stat?.successRate != null ? `${stat.successRate}%` : '—'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Cost</span>
                    <span className="font-medium text-gray-700">
                      ${stat?.costUsd?.toFixed(4) ?? '0.0000'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Arrow connector */}
              {i < AGENTS.length - 1 && (
                <div className="px-1 text-gray-300 text-sm shrink-0">→</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
