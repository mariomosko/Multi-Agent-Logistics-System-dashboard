import { AGENTS } from '../lib/mockGenerator'

const CIN  = 0.000003
const COUT = 0.000015

function Stat({ label, value, sub }) {
  return (
    <div className="p-3 rounded-lg bg-gray-50">
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className="text-lg font-bold text-gray-800">{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-0.5">{sub}</div>}
    </div>
  )
}

const AGENT_BAR_COLORS = {
  blue:    'bg-blue-400',
  violet:  'bg-violet-400',
  amber:   'bg-amber-400',
  emerald: 'bg-emerald-400',
  rose:    'bg-rose-400',
}

export default function CostTracker({ stats }) {
  const {
    totalCost = 0,
    totalInput = 0,
    totalOutput = 0,
    agentStats = [],
    resolved = 0,
  } = stats || {}

  const apiCalls     = agentStats.reduce((s, a) => s + a.runs, 0)
  const avgCostPerEx = resolved > 0 ? totalCost / resolved : 0
  const maxAgentCost = Math.max(...agentStats.map(a => a.costUsd), 0.000001)

  return (
    <div className="space-y-5">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
        Cost Tracking
      </h2>

      {/* Top stats */}
      <div className="grid grid-cols-2 gap-2">
        <Stat
          label="Total API cost"
          value={`$${totalCost.toFixed(4)}`}
          sub={`${apiCalls} API calls`}
        />
        <Stat
          label="Avg cost / exception"
          value={`$${avgCostPerEx.toFixed(4)}`}
          sub={`${resolved} resolved`}
        />
        <Stat
          label="Input tokens"
          value={totalInput.toLocaleString()}
          sub={`$${(totalInput * CIN).toFixed(4)}`}
        />
        <Stat
          label="Output tokens"
          value={totalOutput.toLocaleString()}
          sub={`$${(totalOutput * COUT).toFixed(4)}`}
        />
      </div>

      {/* Per-agent cost breakdown */}
      <div>
        <p className="text-xs text-gray-400 mb-2 uppercase tracking-wider">
          Cost by agent
        </p>
        <div className="space-y-2">
          {AGENTS.map(agent => {
            const s   = agentStats.find(x => x.key === agent.key)
            const cost = s?.costUsd ?? 0
            const pct  = maxAgentCost > 0 ? (cost / maxAgentCost) * 100 : 0
            const bar  = AGENT_BAR_COLORS[agent.color]

            return (
              <div key={agent.key} className="space-y-0.5">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">{agent.label}</span>
                  <span className="font-medium text-gray-700">${cost.toFixed(4)}</span>
                </div>
                <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${bar}`}
                    style={{ width: `${pct}%`, transition: 'width 0.4s ease' }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Token ratio */}
      {(totalInput + totalOutput) > 0 && (
        <div>
          <p className="text-xs text-gray-400 mb-1.5 uppercase tracking-wider">
            Token ratio (input / output)
          </p>
          <div className="flex h-2 rounded-full overflow-hidden">
            <div
              className="bg-blue-300 transition-all"
              style={{ width: `${(totalInput / (totalInput + totalOutput)) * 100}%` }}
            />
            <div className="flex-1 bg-violet-300" />
          </div>
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>{Math.round((totalInput / (totalInput + totalOutput)) * 100)}% input</span>
            <span>{Math.round((totalOutput / (totalInput + totalOutput)) * 100)}% output</span>
          </div>
        </div>
      )}
    </div>
  )
}
