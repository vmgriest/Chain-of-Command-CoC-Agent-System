# Chain of Command (CoC) — Implementation Plan

Companion to [README.md](README.md) (what the system is) and [CHECKLIST.md](CHECKLIST.md) (task-by-task execution).

---

## Context

The repo is greenfield. The README describes a four-tier support chatbot (Front Desk → Department Manager → VP → CEO) where escalation is a real handoff — the agent, its tool access, and the UI all change. This plan turns that description into a build order.

The core risk is building four agents in isolation and discovering at integration time that the thing connecting them — the handoff — was an afterthought. So the approach is a **thin vertical slice first**: all four tiers wired end-to-end with stubbed tools but a *real* handoff protocol, a *real* human-in-the-loop consent gate, and *real* per-tier UI theming. Demoable from milestone 1, then each tier deepened in place.

**Decisions locked:**

| Decision | Choice |
|---|---|
| Frontend | React + TypeScript + Vite |
| Sequencing | Vertical slice, then depth |
| Real in M1 | Handoff protocol, HITL consent gate, per-tier theming |
| Stubbed in M1 | Tools, RAG, MCP, Docker sandboxing (hardened in M2–M3) |
| Models | Ollama only, config-driven, CEO capped at ~32B |

---

## Architectural decisions to settle before writing tier code

**1. The handoff packet is the contract, not the transcript.**
Every tier receives a typed `HandoffPacket` (Pydantic), never raw message history. Define this schema *first* — it determines each tier's state shape, what the summarizer extracts, and where PII redaction happens. `ruled_out` and `attempted_actions` are what stop each tier re-litigating dead ends.

**2. Tiers cannot promote themselves.**
The supervisor node owns all transitions. A tier's subgraph returns an `EscalationRequest`; the supervisor decides whether to honor it and routes through the consent interrupt. Keeps escalation auditable and prevents prompt-injected self-promotion.

**3. Tool registries are built at startup, per tier, and are empty where they should be.**
The Front Desk agent gets an empty tool list — not a filtered one. There is no runtime path for it to call a tool, so no prompt can talk it into one. This is the security property worth protecting; don't let a later refactor turn it into a filter.

**4. One state object, checkpointed from day one.**
LangGraph `MemorySaver` in dev, Postgres checkpointer later. HITL interrupts and reconnect-after-reload both depend on this, so wire the checkpointer in M1 even though it looks premature.

---

## Milestone 1 — Vertical slice (the spine)

**Goal:** A user chats with Penny, hits a question she can't answer, is asked "shall I bring in a manager?", approves, and watches the UI transition to Dwight — who introduces himself and demonstrably knows what was already tried. All four tiers reachable. Tools are stubs.

### Backend

**Config layer** — `backend/config/schema.py`, `loader.py`
- Pydantic models for `company_config.json` as specced in the README (company, personas, models, knowledge, mcp_servers, escalation).
- Validate at import. Reject non-allowlisted stdio binaries here even though sandboxing lands in M3 — the allowlist (`uvx`, `npx`, `docker`) is a cheap parse-time check.
- `company_config.example.json` committed; the real one gitignored.

**Handoff protocol** — `backend/graph/handoff.py` ← *write this first*
- `HandoffPacket`: `ticket_id`, `customer_intent`, `verified_facts[]`, `attempted_actions[]`, `ruled_out[]`, `open_questions[]`, `sentiment`, `escalation_reason`, `pii_redacted`.
- `summarize_for_handoff(state, from_tier, to_tier) -> HandoffPacket` — structured-output LLM call given the transcript *and* the incoming packet, so facts accumulate rather than reset.
- Size cap: field-level `max_length` on lists plus a token budget check that triggers re-summarization.
- Redaction at the boundary — regex for emails/phones/card numbers to start.

**Graph** — `backend/graph/`
- `state.py` — `CoCState`: messages, current_tier, packet, attempt_count, pending_escalation, session metadata.
- `tiers/base.py` ← *write this second.* Shared tier loop factory: takes persona, model, tool list, prompt template; returns a compiled subgraph. All four tiers are instances of it. Writing this before any individual tier is what keeps them from drifting into four bespoke implementations.
- `tiers/{front_desk,manager,vice_president,ceo}.py` — thin config over `base.py`. In M1, Manager/VP/CEO get one or two obviously-stubbed tools so tool-calling plumbing is exercised.
- `supervisor.py` — routes to the active tier, receives escalation requests, invokes the consent interrupt, calls the summarizer, advances tier.

**HITL middleware** — `backend/graph/middleware/hitl.py`
LangGraph `interrupt()` for two distinct cases:
- **Escalation consent** — agent-initiated escalation pauses and asks. User-initiated escalation skips the gate.
- **Context request** — agent needs an account number, order ID, etc. Critically *conditional*: if the agent needs nothing, the loop runs uninterrupted. Not a per-turn checkpoint.

Both resume cleanly from checkpoint after a reconnect.

**Escalation detection**
- User-initiated: small structured-output classifier per user turn (`wants_escalation: bool`), not keyword matching.
- Agent-initiated: tier structured output carries `can_resolve: bool` + `escalation_reason`, plus a hard cap from `escalation.max_attempts_per_tier`.
- **No auto-descalation, ever.** Once at tier N, simple follow-ups are answered at tier N.

**API** — `backend/api/main.py`
FastAPI, `WebSocket /ws/chat/{session_id}` streaming tokens plus typed control events: `tier_change`, `escalation_prompt`, `context_request`, `agent_intro`. The frontend needs to know *why* it's re-theming, so transitions are explicit events, not something the client infers from message content.

### Frontend — `frontend/`

- Vite + React + TS + Tailwind. Zustand for chat state, `useEscalation` hook for the WS control channel.
- `themes/` — one theme object per tier (color, avatar, badge, background), keyed off `personas[].theme` in config, so renaming personas re-themes without a code change.
- Escalation transition via Framer Motion: old agent fades, tier-change divider animates in, new agent's introduction streams in. This is the moment the whole concept lands — spend the time on it.
- Consent and context-request prompts as inline chat affordances, not modals.

### Infra
`docker-compose.yml` for Qdrant + Ollama. `pyproject.toml` with `uv`. Ruff + mypy.

**Exit criteria:** four-tier escalation demo works; handoff packets visibly carry facts forward; refreshing the browser mid-interrupt resumes correctly.

---

## Milestone 2 — Department Manager gets real (RAG + local tools)

- `backend/rag/ingest.py` — PDF (pypdf), Markdown, and crawl → chunk → embed (`nomic-embed-text` via Ollama) → Qdrant. Idempotent, content-hashed so re-runs don't duplicate.
- `backend/rag/retriever.py` — hybrid search + payload filtering, returning source metadata so the agent can cite.
- Replace stubs with real tools: `rag_search`, `scrape_url` (allowlisted domains only).
- Structured output on Manager responses so the CEO tier can later consume typed data.
- Code sandbox tool: Docker exec, no network, read-only rootfs, CPU/mem/wall-clock caps.

**Exit:** Manager answers a question from an ingested PDF with citations that the Front Desk provably cannot.

---

## Milestone 3 — Vice President + the security model

- `backend/mcp/registry.py` — parse `mcp_servers`, spawn stdio subprocesses / open HTTP connections at startup, inject into the tiers listed in each server's `tiers` array. Use `langchain-mcp-adapters`.
- `backend/mcp/sandbox.py` — **harden here.** Allowlist enforced at spawn, not just parse. Local MCP servers in Docker: non-root, dropped caps, read-only root, explicit mount allowlist, egress restricted to declared endpoints.
- `backend/mcp/internal_server.py` — first-party tools over MCP so internal and external tooling share one interface.
- Async tool fan-out: `asyncio.gather` over independent tool calls in the VP loop.
- Wire a real external server to prove the external path.

**Exit:** VP resolves something requiring live web search; a config entry with a disallowed binary is rejected before any process spawns.

---

## Milestone 4 — CEO tier

- Evaluator–optimizer loop: draft → self-critique against the user's stated goal → revise, bounded by iteration count and token budget. The evaluator is a separate structured-output call with explicit pass/fail criteria, not a vibe check.
- `backend/notifications/` — SMTP to `human_admin.email`, Web Push to `push_topic`, scheduling link surfaced to the customer.
- **Session continuity:** on human escalation, emit `human_escalation`, tell the user exactly what was done and what to expect, and **keep the session live**. The user keeps chatting; the CEO keeps answering.

**Exit:** CEO exhausts its own tooling, emails the admin, and the conversation continues normally afterward.

---

## Milestone 5 — Guardrails, observability, polish

- `middleware/guardrails.py` — input (injection, PII, abuse, scope) at Front Desk; output (hallucinated commitments, internal leakage, unsafe advice) at CEO.
- LangSmith or OTel tracing with spans crossing tier boundaries — one trace per ticket, not per tier.
- Config hot reload.
- Analytics: escalation rate, resolution-per-tier, time-to-resolution — the payoff metric for the whole tiering argument.
- Tests: pytest for handoff summarization, escalation routing, allowlist rejection. Vitest for the escalation UI transition.

---

## Files to create (representative)

```
backend/config/{schema,loader}.py          # company_config.json → typed
backend/graph/state.py                     # CoCState
backend/graph/handoff.py                   # HandoffPacket + summarizer  ← first
backend/graph/tiers/base.py                # shared tier loop factory     ← second
backend/graph/tiers/{front_desk,manager,vice_president,ceo}.py
backend/graph/supervisor.py                # routing, escalation, transitions
backend/graph/middleware/{hitl,guardrails}.py
backend/mcp/{registry,sandbox,internal_server}.py
backend/rag/{ingest,retriever}.py
backend/notifications/{email,push,scheduling}.py
backend/api/main.py                        # FastAPI + WebSocket
frontend/src/hooks/useEscalation.ts
frontend/src/themes/index.ts
frontend/src/components/Chat/
company_config.example.json
docker-compose.yml
```

---

## Verification

**M1 (the one that matters most):**
1. `docker compose up -d`; pull models; start backend and frontend.
2. Ask Penny something in-scope → answered at tier 1, no escalation.
3. Ask something requiring a lookup → she explains she can't and asks consent. Decline → continues at tier 1. Ask again, accept → UI transitions, Dwight introduces himself.
4. Confirm Dwight references what was already tried without you repeating it — inspect the `HandoffPacket` and check `ruled_out` is populated.
5. Say "I want to talk to upper management" → immediate escalation, no consent prompt.
6. Trigger a context request → refresh the browser mid-prompt → session resumes at the interrupt.
7. Assert Front Desk's tool registry is empty in a test, and try prompt-injecting a tool call.

**M2:** query a fact that exists only in an ingested PDF; verify citation; verify Front Desk fails the same question.
**M3:** a `command: "bash"` config entry is rejected at startup. Inspect the running MCP container: non-root, read-only rootfs.
**M4:** force CEO exhaustion; admin email arrives, user is told what happened, follow-up still answered in-session.
**M5:** one trace spans all four tiers for a single ticket.

---

## Open items to decide later

- Auth on the chat session (currently anonymous) — matters before any real deployment.
- Postgres checkpointer + conversation persistence beyond process lifetime.
- Multi-tenant: one deployment serving several `company_config.json` files vs. one per company.
