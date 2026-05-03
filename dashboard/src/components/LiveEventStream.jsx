const SEVERITY_COLORS = {
  low:      'bg-green-100 text-green-700',
  medium:   'bg-yellow-100 text-yellow-700',
  high:     'bg-orange-100 text-orange-700',
  critical: 'bg-red-100 text-red-700',
}

const STATUS_COLORS = {
  detecting:     'text-blue-500',
  analyzing:     'text-violet-500',
  deciding:      'text-amber-500',
  communicating: 'text-emerald-500',
  acting:        'text-rose-500',
  resolved:      'text-green-600',
  failed:        'text-red-500',
}

function statusDot(status) {
  const isActive  = !['resolved', 'failed'].includes(status)
  const colorCls  = STATUS_COLORS[status] || 'text-gray-400'
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${colorCls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'animate-pulse' : ''} bg-current`} />
      {status}
    </span>
  )
}

export default function LiveEventStream({ exceptions }) {
  const recent = [...exceptions].reverse().slice(0, 40)

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">
          Live Event Stream
        </h2>
        <span className="text-xs text-gray-400">{exceptions.length} total</span>
      </div>

      <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
        {recent.length === 0 && (
          <p className="text-xs text-gray-400 text-center mt-8">Waiting for events…</p>
        )}
        {recent.map(exc => (
          <div
            key={exc.id}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-50 border border-gray-100 text-xs"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-gray-500 truncate">{exc.tracking_number}</span>
                <span className="text-gray-300">·</span>
                <span className="text-gray-500">{exc.carrier}</span>
              </div>
              <div className="text-gray-600 truncate mt-0.5">{exc.exception_type.replace('_', ' ')}</div>
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0">
              <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${SEVERITY_COLORS[exc.severity] || 'bg-gray-100 text-gray-500'}`}>
                {exc.severity}
              </span>
              {statusDot(exc.workflow_status)}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
