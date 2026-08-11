/**
 * HTTP client for the non-WebSocket endpoints.
 */

import type { PublicConfig } from '@/types';

// import.meta.env is Vite's env-var mechanism (not process.env — this runs in
// the browser, not Node). Empty string by default: fetch('' + '/api/config')
// is just '/api/config', a same-origin request that Vite's dev-server proxy
// (vite.config.ts) forwards to the real backend — no CORS to configure.
// Set VITE_API_BASE only when the frontend is served from a different origin
// than the backend (e.g. separate production domains).
const API_BASE = import.meta.env.VITE_API_BASE ?? '';

/** GET /api/config — personas and themes, fetched once at app mount. */
export async function fetchConfig(): Promise<PublicConfig> {
  const res = await fetch(`${API_BASE}/api/config`);
  if (!res.ok) {
    throw new Error(`GET /api/config failed: ${res.status}`);
  }
  return (await res.json()) as PublicConfig;
}

/** GET /api/health — backend, Ollama, Qdrant, MCP server liveness. */
export async function fetchHealth(): Promise<Record<string, boolean>> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) {
    throw new Error(`GET /api/health failed: ${res.status}`);
  }
  return (await res.json()) as Record<string, boolean>;
}

/** Builds ws:// or wss:// from window.location so it works in dev and behind
 *  TLS in production without a second config knob. */
export function wsUrl(sessionId: string): string {
  if (!API_BASE) {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${wsProtocol}//${window.location.host}/ws/chat/${sessionId}`;
  }
  const httpUrl = new URL(API_BASE, window.location.origin);
  const wsProtocol = httpUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${wsProtocol}//${httpUrl.host}/ws/chat/${sessionId}`;
}

const SESSION_STORAGE_KEY = 'coc_session_id';

/** crypto.randomUUID(), persisted to localStorage so a refresh reconnects to
 *  the same conversation rather than silently starting a new one. */
export function newSessionId(): string {
  const existing = localStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const id = crypto.randomUUID();
  localStorage.setItem(SESSION_STORAGE_KEY, id);
  return id;
}