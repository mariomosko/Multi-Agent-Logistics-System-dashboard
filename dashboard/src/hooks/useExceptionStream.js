import { useCallback, useEffect, useRef, useState } from 'react'
import { applyWsEvent, fetchExceptions, normalizeSummary } from '../lib/api'

// Uses current page host so the connection routes correctly in every environment:
// - Vite dev server (port 5173) → Vite proxy → backend :8000
// - Docker dev  (port 5173 exposed) → same path above
// - Production nginx (port 80) → nginx proxies /api/v1/ws → backend :8000
const WS_SCHEME = window.location.protocol === 'https:' ? 'wss' : 'ws'
const WS_URL = `${WS_SCHEME}://${window.location.host}/api/v1/ws`
const RECONNECT_DELAY_MS = 3000

/**
 * Manages the full real-time exception state:
 *   - Initial load via GET /monitoring/exceptions
 *   - Live updates via WebSocket (agent.started / agent.completed / etc.)
 *   - Exponential-backoff reconnection on disconnect
 *
 * Returns { exceptions, wsStatus, triggerSimulation }
 * wsStatus: 'connecting' | 'connected' | 'disconnected' | 'error'
 */
export function useExceptionStream() {
  const [exceptions, setExceptions] = useState([])
  const [wsStatus,   setWsStatus]   = useState('connecting')

  const wsRef             = useRef(null)
  const reconnectTimerRef = useRef(null)
  const mountedRef        = useRef(true)

  // ── Initial REST load ───────────────────────────────────────────────────────
  useEffect(() => {
    fetchExceptions(50)
      .then(data => {
        if (!mountedRef.current) return
        setExceptions(data.items.map(normalizeSummary))
      })
      .catch(err => console.warn('[api] Initial load failed:', err.message))
  }, [])

  // ── WebSocket ───────────────────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (!mountedRef.current) return
    setWsStatus('connecting')

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return }
      setWsStatus('connected')
      console.info('[ws] connected')
    }

    ws.onmessage = (ev) => {
      if (!mountedRef.current) return
      try {
        const msg = JSON.parse(ev.data)
        setExceptions(prev => applyWsEvent(prev, msg))
      } catch (e) {
        console.warn('[ws] bad message', e)
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setWsStatus('disconnected')
      console.info(`[ws] disconnected — reconnecting in ${RECONNECT_DELAY_MS}ms`)
      reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
    }

    ws.onerror = () => {
      // onclose fires immediately after onerror — handle there
      setWsStatus('error')
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { exceptions, setExceptions, wsStatus }
}
