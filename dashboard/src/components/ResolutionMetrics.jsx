const TYPE_LABELS = {
  delay:          'Delay',
  lost:           'Lost',
  damaged:        'Damaged',
  address_issue:  'Address Issue',
  customs_hold:   'Customs Hold',
  failed_delivery:'Failed Delivery',
}

const RESOLUTION_LABELS = {
  reroute:             'Reroute',
  reship:              'Reship',
  refund:              'Refund',
  contact_carrier:     'Contact Carrier',
  schedule_redelivery: 'Redeliver',
  monitor:             'Monitor',
  escalate:            'Escalate',
}

function MiniBar({ label, value, max, color }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-24 text-gray-500 truncate">{label}</span>
      <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${pct}%`, transition: 'width 0.4s ease' }}
        />
      </div>
      <span className="w-6 text-right font-medium text-gray-700">{value}</span>
    </div>
  )
}

function DonutSegment({ resolved, failed, active }) {
  const total = resolved + failed + active || 1
  const rPct = (resolved / total) * 100
  const fPct = (failed  / total) * 100
  const aPct = (active  / total) * 100

  // Simple stacked bar as a donut proxy (pure CSS)
  return (
    <div className="relative">
      <div className="flex rounded-full overflow-hidden h-3 w-full">
        <div className="bg-green-400  transition-all" style={{ width: `${rPct}%` }} title={`Resolved: ${resolved}`} />
        <div className="bg-red-400    transition-all" style={{ width: `${fPct}%` }} title={`Failed: ${failed}`} />
        <div className="bg-blue-300   transition-all" style={{ width: `${aPct}%` }} title={`Active: ${active}`} />
        <div className="flex-1 bg-gray-100" />
      </div>
    </div>
  )
}

export default function ResolutionMetrics({ stats }) {
  const { resolved = 0, failed = 0, active = 0, bySeverity = {}, byType = {} } = stats || {}
  const total = resolved + failed + active

  const typeEntries   = Object.entries(byType).sort((a, b) => b[1] - a[1])
  const typeMax       = Math.max(...Object.values(byType), 1)

  const resolutionCounts = {}
  // we aggregate resolution_type separately from agentStats — passed via stats.byResolution
  const resEntries = Object.entries(stats?.byResolution || {}).sort((a, b) => b[1] - a[1])
  const resMax     = Math.max(...resEntries.map(e => e[1]), 1)

  return (
    <div className="space-y-5">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
        Resolution Outcomes
      </h2>

      {/* Summary bar */}
      <div>
        <DonutSegment resolved={resolved} failed={failed} active={active} />
        <div className="flex gap-4 mt-2 text-xs text-gray-500">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-400" />{resolved} resolved</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400"   />{failed} failed</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-300"  />{active} active</span>
        </div>
      </div>

      {/* Success rate */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
        <span className="text-xs text-gray-500">Success rate</span>
        <span className={`text-lg font-bold ${
          total === 0 ? 'text-gray-400' :
          (resolved / (resolved + failed)) >= 0.9 ? 'text-green-600' :
          (resolved / (resolved + failed)) >= 0.7 ? 'text-yellow-600' : 'text-red-500'
        }`}>
          {total === 0 ? '—' : `${Math.round((resolved / (resolved + failed || 1)) * 100)}%`}
        </span>
      </div>

      {/* By severity */}
      <div>
        <p className="text-xs text-gray-400 mb-2 uppercase tracking-wider">By severity</p>
        <div className="space-y-1.5">
          {[
            { key: 'critical', color: 'bg-red-400' },
            { key: 'high',     color: 'bg-orange-400' },
            { key: 'medium',   color: 'bg-yellow-400' },
            { key: 'low',      color: 'bg-green-400' },
          ].map(({ key, color }) => (
            <MiniBar
              key={key}
              label={key.charAt(0).toUpperCase() + key.slice(1)}
              value={bySeverity[key] || 0}
              max={total || 1}
              color={color}
            />
          ))}
        </div>
      </div>

      {/* By exception type */}
      <div>
        <p className="text-xs text-gray-400 mb-2 uppercase tracking-wider">By type</p>
        <div className="space-y-1.5">
          {typeEntries.map(([type, count]) => (
            <MiniBar
              key={type}
              label={TYPE_LABELS[type] || type}
              value={count}
              max={typeMax}
              color="bg-violet-400"
            />
          ))}
          {typeEntries.length === 0 && (
            <p className="text-xs text-gray-400">No data yet</p>
          )}
        </div>
      </div>

      {/* By resolution type */}
      {resEntries.length > 0 && (
        <div>
          <p className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Resolutions</p>
          <div className="space-y-1.5">
            {resEntries.map(([type, count]) => (
              <MiniBar
                key={type}
                label={RESOLUTION_LABELS[type] || type}
                value={count}
                max={resMax}
                color="bg-emerald-400"
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
