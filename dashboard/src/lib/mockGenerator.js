// Mock data generator — simulates a live logistics exception pipeline

export const AGENTS = [
  { key: 'detection',     label: 'Detection',     color: 'blue' },
  { key: 'analysis',      label: 'Analysis',      color: 'violet' },
  { key: 'decision',      label: 'Decision',      color: 'amber' },
  { key: 'communication', label: 'Communication', color: 'emerald' },
  { key: 'action',        label: 'Action',        color: 'rose' },
]

const EXCEPTION_TYPES   = ['delay', 'lost', 'damaged', 'address_issue', 'customs_hold', 'failed_delivery']
const CARRIERS          = ['FedEx', 'UPS', 'USPS', 'DHL']
const SEVERITIES        = ['low', 'medium', 'high', 'critical']
const RESOLUTION_TYPES  = ['reroute', 'reship', 'refund', 'contact_carrier', 'schedule_redelivery', 'monitor']

const LOCATIONS = [
  'Memphis, TN', 'Louisville, KY', 'Austin, TX', 'Dallas, TX',
  'Chicago, IL', 'Los Angeles, CA', 'Atlanta, GA', 'New York, NY',
]

// ── Mock output pools per agent × exception type ─────────────────────────────

const DETECTION_OUTPUTS = {
  delay:          [
    { confidence: 0.94, summary: 'Severe weather event grounded all outbound flights at sorting hub.' },
    { confidence: 0.89, summary: 'Mechanical breakdown at main conveyor halted overnight sorting operations.' },
  ],
  lost:           [
    { confidence: 0.97, summary: 'No scan activity for 6 days — package likely misrouted during high-volume sort.' },
    { confidence: 0.92, summary: 'System alert triggered after 144 hours without any location update.' },
  ],
  damaged:        [
    { confidence: 0.98, summary: 'Forklift impact detected at sorting facility — outer carton visibly crushed.' },
    { confidence: 0.95, summary: 'Package sustained water damage during unloading in adverse conditions.' },
  ],
  address_issue:  [
    { confidence: 0.93, summary: 'Delivery failed: apartment number absent from shipping label.' },
    { confidence: 0.88, summary: 'Address flagged as undeliverable — building not found in postal database.' },
  ],
  customs_hold:   [
    { confidence: 0.96, summary: 'CBP flagged shipment for supplemental documentation review.' },
    { confidence: 0.91, summary: 'HS tariff code inconsistency detected against declared commercial invoice.' },
  ],
  failed_delivery:[
    { confidence: 0.90, summary: 'Driver unable to complete delivery — no access and no safe-drop location.' },
    { confidence: 0.87, summary: 'Three delivery attempts failed; recipient unreachable during all windows.' },
  ],
}

const ANALYSIS_OUTPUTS = {
  delay: [
    { root_cause: 'Category 3 storm forced 18-hour hub closure, grounding 47 flights and delaying 12,000+ packages.', estimated_delay_days: 3, recommended_urgency: 'expedited' },
    { root_cause: 'Conveyor motor failure halted overnight sort; repair complete but backlog requires 24h clearance.', estimated_delay_days: 1, recommended_urgency: 'routine' },
  ],
  lost: [
    { root_cause: 'Package likely misrouted during holiday surge; barcode may have been damaged mid-sort causing misread.', estimated_delay_days: 7, recommended_urgency: 'immediate' },
    { root_cause: 'Manual sort override during system outage placed package in incorrect destination cage.', estimated_delay_days: 5, recommended_urgency: 'expedited' },
  ],
  damaged: [
    { root_cause: 'Inadequate original packaging; contents shifted under 80 lbs of stacked parcels during transit.', estimated_delay_days: 4, recommended_urgency: 'immediate' },
    { root_cause: 'Forklift tine punctured outer carton during unloading. Facility confirmed operator error.', estimated_delay_days: 2, recommended_urgency: 'expedited' },
  ],
  address_issue: [
    { root_cause: 'Shipper omitted apartment number; USPS database shows 24 units at this street address.', estimated_delay_days: 3, recommended_urgency: 'expedited' },
    { root_cause: 'Address label printed from incomplete customer profile — secondary address line left blank.', estimated_delay_days: 2, recommended_urgency: 'routine' },
  ],
  customs_hold: [
    { root_cause: 'Commercial invoice value inconsistent with HS code; CBP requires importer clarification before release.', estimated_delay_days: 5, recommended_urgency: 'expedited' },
    { root_cause: 'First-time importer flagged for enhanced review; standard supplemental documentation required.', estimated_delay_days: 7, recommended_urgency: 'expedited' },
  ],
  failed_delivery: [
    { root_cause: 'Recipient unreachable after 3 attempts; no safe-drop authorization or neighbor delivery option.', estimated_delay_days: 2, recommended_urgency: 'routine' },
    { root_cause: 'Delivery window mismatch — customer works nights; standard daytime attempts consistently fail.', estimated_delay_days: 1, recommended_urgency: 'routine' },
  ],
}

const DECISION_OUTPUTS = {
  delay: [
    { resolution_type: 'contact_carrier', notify_customer: true,  rationale: 'Contact hub ops to expedite reroute and set priority flag; update customer with revised ETA.', action_count: 2 },
    { resolution_type: 'monitor',          notify_customer: false, rationale: 'Delay within SLA window. Monitor for 24h; notify customer only if delay extends further.', action_count: 1 },
  ],
  lost: [
    { resolution_type: 'reship', notify_customer: true, rationale: 'Package unrecoverable after 6-day trace window. Authorize replacement shipment and open insurance claim.', action_count: 3 },
  ],
  damaged: [
    { resolution_type: 'reship', notify_customer: true, rationale: 'Damage assessment confirms contents compromised. Reship immediately with enhanced protective packaging.', action_count: 2 },
    { resolution_type: 'refund', notify_customer: true, rationale: 'Contents fully destroyed per damage report. Issue full refund and file carrier liability claim.', action_count: 2 },
  ],
  address_issue: [
    { resolution_type: 'schedule_redelivery', notify_customer: true, rationale: 'Contact customer to confirm corrected address, then schedule redelivery within next business day.', action_count: 2 },
  ],
  customs_hold: [
    { resolution_type: 'contact_carrier', notify_customer: true, rationale: 'Engage customs broker; submit supplemental HS declaration and invoice to CBP within 48h.', action_count: 3 },
  ],
  failed_delivery: [
    { resolution_type: 'schedule_redelivery', notify_customer: true, rationale: 'Offer customer-selected delivery window to prevent further missed attempts and return-to-sender.', action_count: 2 },
  ],
}

const COMM_OUTPUTS = {
  delay:          { subject: 'Shipment delay notice — updated delivery estimate', tone: 'apologetic',     message_preview: 'We wanted to let you know your package has been delayed due to severe weather at our hub. We\'re working to get it moving as quickly as possible and have updated your estimated delivery date.' },
  lost:           { subject: 'Important: your shipment is being investigated',    tone: 'urgent',        message_preview: 'We\'re sorry to inform you that we\'ve lost track of your shipment and have opened an urgent investigation. Our team is actively working to locate your package.' },
  damaged:        { subject: 'Your shipment was damaged in transit',              tone: 'apologetic',     message_preview: 'We sincerely apologize — your package sustained damage during transit. We\'ve already begun processing a replacement shipment which will be dispatched within 24 hours.' },
  address_issue:  { subject: 'Action required: delivery address update needed',   tone: 'informational', message_preview: 'We were unable to deliver your package because we need a small correction to your address. Please reply with your apartment or unit number so we can reattempt delivery.' },
  customs_hold:   { subject: 'Customs processing update for your shipment',       tone: 'informational', message_preview: 'Your international shipment is currently undergoing standard customs review. To expedite clearance, please provide a copy of your commercial invoice at your earliest convenience.' },
  failed_delivery:{ subject: 'Missed delivery — schedule your redelivery',        tone: 'informational', message_preview: 'We attempted to deliver your package but were unable to reach you. Please select a convenient 2-hour delivery window using the link below to ensure a successful redelivery.' },
}

const ACTION_OUTPUTS = {
  delay:          { overall_status: 'resolved',          notes: 'Carrier priority flag set. Reroute via alternate hub confirmed. Tracking ETA updated.' },
  lost:           { overall_status: 'resolved',          notes: 'Carrier trace ticket #TRC-2026-8821 opened. Replacement dispatched. Insurance claim pending.' },
  damaged:        { overall_status: 'resolved',          notes: 'Carrier damage claim #CLM-887432 filed. Replacement shipped via 2-day priority with foam inserts.' },
  address_issue:  { overall_status: 'resolved',          notes: 'Customer confirmed Apt 4B. Corrected label generated. Redelivery booked for next business day 10AM–2PM.' },
  customs_hold:   { overall_status: 'partially_resolved',notes: 'Customs broker engaged. Supplemental HS declaration submitted. Awaiting CBP portal confirmation.' },
  failed_delivery:{ overall_status: 'resolved',          notes: 'Customer selected Thu 2–4 PM window. Driver notification queued for Wednesday dispatch.' },
}

// Simulated API call durations per agent (ms)
const DURATION_RANGES = {
  detection: [800, 1800], analysis: [1400, 3200], decision: [1000, 2600],
  communication: [700, 1800], action: [1100, 2800],
}

// ── Helpers ──────────────────────────────────────────────────────────────────

let _id = 1
const randOf  = arr => arr[Math.floor(Math.random() * arr.length)]
const randInt = (lo, hi) => Math.floor(Math.random() * (hi - lo + 1)) + lo
const trackingNum = () =>
  `${randOf(['FX', 'UP', 'US', 'DH'])}${String(randInt(1e8, 9e8))}`

function makeAgentOutput(agentKey, exceptionType) {
  const type = exceptionType in DETECTION_OUTPUTS ? exceptionType : 'delay'
  switch (agentKey) {
    case 'detection':     return randOf(DETECTION_OUTPUTS[type])
    case 'analysis':      return randOf(ANALYSIS_OUTPUTS[type])
    case 'decision':      return randOf(DECISION_OUTPUTS[type] || DECISION_OUTPUTS.delay)
    case 'communication': return COMM_OUTPUTS[type] || COMM_OUTPUTS.delay
    case 'action': {
      const base = ACTION_OUTPUTS[type] || ACTION_OUTPUTS.delay
      return { ...base, executed_count: randInt(1, 3) }
    }
    default: return null
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

export function generateException() {
  const type = randOf(EXCEPTION_TYPES)
  return {
    id: _id++,
    tracking_number: trackingNum(),
    carrier: randOf(CARRIERS),
    exception_type: type,
    severity: randOf(SEVERITIES),
    description: null,
    location: randOf(LOCATIONS),
    detected_at: new Date().toISOString(),
    workflow_status: 'detecting',
    agent_statuses:  { detection: 'running', analysis: 'idle', decision: 'idle', communication: 'idle', action: 'idle' },
    agent_outputs:   { detection: null, analysis: null, decision: null, communication: null, action: null },
    agent_durations: {},
    agent_costs:     {},
    resolution_type: null,
  }
}

// Advance one pipeline step. Returns updated exception (never null).
export function advancePipeline(exc) {
  const pipeline   = ['detection', 'analysis', 'decision', 'communication', 'action']
  const statusMap  = { ...exc.agent_statuses }
  const outputMap  = { ...exc.agent_outputs }
  const durationMap = { ...exc.agent_durations }
  const costMap    = { ...exc.agent_costs }

  const currentIdx = pipeline.findIndex(a => statusMap[a] === 'running')
  if (currentIdx === -1) return exc   // nothing running — no-op

  const agent = pipeline[currentIdx]

  // 8% failure rate
  if (Math.random() < 0.08) {
    statusMap[agent] = 'failed'
    return { ...exc, agent_statuses: statusMap, agent_outputs: outputMap,
             agent_durations: durationMap, agent_costs: costMap, workflow_status: 'failed' }
  }

  // Complete current agent
  statusMap[agent]   = 'completed'
  outputMap[agent]   = makeAgentOutput(agent, exc.exception_type)
  const [dlo, dhi]   = DURATION_RANGES[agent]
  durationMap[agent] = randInt(dlo, dhi)
  const inputTok     = randInt(300, 900)
  const outputTok    = randInt(100, 400)
  costMap[agent]     = { input: inputTok, output: outputTok }

  // Start next agent
  const next = pipeline[currentIdx + 1]
  if (next) {
    statusMap[next] = 'running'
    const nextWorkflow = {
      analysis: 'analyzing', decision: 'deciding',
      communication: 'communicating', action: 'acting',
    }[next] || 'detecting'
    return {
      ...exc,
      agent_statuses: statusMap, agent_outputs: outputMap,
      agent_durations: durationMap, agent_costs: costMap,
      workflow_status: nextWorkflow,
      resolution_type: next === 'action' ? (
        outputMap.decision?.resolution_type ?? randOf(RESOLUTION_TYPES)
      ) : exc.resolution_type,
    }
  }

  // Pipeline finished
  return {
    ...exc,
    agent_statuses: statusMap, agent_outputs: outputMap,
    agent_durations: durationMap, agent_costs: costMap,
    workflow_status: 'resolved',
    resolution_type: outputMap.decision?.resolution_type ?? exc.resolution_type ?? randOf(RESOLUTION_TYPES),
  }
}

// ── Aggregate stats ───────────────────────────────────────────────────────────

const CIN  = 0.000003
const COUT = 0.000015

export function exceptionCost(exc) {
  return Object.values(exc.agent_costs).reduce(
    (sum, { input, output }) => sum + input * CIN + output * COUT, 0
  )
}

export function totalStats(exceptions) {
  const resolved = exceptions.filter(e => e.workflow_status === 'resolved').length
  const failed   = exceptions.filter(e => e.workflow_status === 'failed').length
  const active   = exceptions.filter(
    e => !['resolved', 'failed'].includes(e.workflow_status)
  ).length

  const bySeverity = { low: 0, medium: 0, high: 0, critical: 0 }
  const byType     = {}
  let totalCost    = 0
  let totalInput   = 0
  let totalOutput  = 0

  for (const e of exceptions) {
    if (e.severity) bySeverity[e.severity] = (bySeverity[e.severity] || 0) + 1
    byType[e.exception_type] = (byType[e.exception_type] || 0) + 1
    totalCost   += exceptionCost(e)
    for (const { input, output } of Object.values(e.agent_costs)) {
      totalInput  += input
      totalOutput += output
    }
  }

  const agentStats = AGENTS.map(a => {
    const runs      = exceptions.filter(e => e.agent_statuses[a.key] !== 'idle').length
    const successes = exceptions.filter(e => e.agent_statuses[a.key] === 'completed').length
    const failures  = exceptions.filter(e => e.agent_statuses[a.key] === 'failed').length
    const costs     = exceptions.map(e => e.agent_costs[a.key]).filter(Boolean)
    const inp  = costs.reduce((s, c) => s + c.input, 0)
    const out  = costs.reduce((s, c) => s + c.output, 0)
    return {
      ...a,
      runs, successes, failures,
      successRate: runs ? Math.round((successes / runs) * 100) : null,
      costUsd: inp * CIN + out * COUT,
    }
  })

  return { resolved, failed, active, bySeverity, byType, totalCost, totalInput, totalOutput, agentStats }
}
