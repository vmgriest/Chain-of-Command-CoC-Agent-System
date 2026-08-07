/**
 * HTTP client for the non-WebSocket endpoints.
 */

import type { PublicConfig } from '@/types';

// TODO(M1): API_BASE from import.meta.env.VITE_API_BASE, defaulting to '' so the
//   Vite dev proxy handles it (see vite.config.ts).

/** TODO(M1): GET /api/config — personas and themes, fetched once at app mount. */
export async function fetchConfig(): Promise<PublicConfig> {
  throw new Error('not implemented');
}

/** TODO(M1): GET /api/health — backend, Ollama, Qdrant, MCP server liveness. */
export async function fetchHealth(): Promise<Record<string, boolean>> {
  throw new Error('not implemented');
}

// TODO(M1): wsUrl(sessionId) — build ws:// or wss:// from window.location so it
//   works in dev and behind TLS in production without a second config knob.

// TODO(M1): newSessionId() — crypto.randomUUID(), persisted to localStorage.