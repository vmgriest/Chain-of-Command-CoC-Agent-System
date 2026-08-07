# Build Checklist

Task-by-task execution list for [PLAN.md](PLAN.md). Ordered — later items assume earlier ones. Two files are marked ⭐ **write first**: everything else is shaped by them.

---

## M0 — Pre-flight

Verify the toolchain before writing code. On this machine `python 3.12.10` and `uv 0.11.28` are confirmed; `node`, `ollama`, and `docker` were **not on the Git Bash PATH** and need checking (they may be installed but not exported to that shell).

- [ ] `python --version` → 3.11+ ✅ *(3.12.10 confirmed)*
- [ ] `uv --version` ✅ *(0.11.28 confirmed)*
- [ ] `node --version` → 20+ ⚠️ *not found on PATH — verify install*
- [ ] `docker --version` + `docker compose version` ⚠️ *not found on PATH — verify install*
- [ ] `ollama --version` ⚠️ *not found on PATH — verify install*
- [ ] Decide CEO-tier model from actual available RAM/VRAM (target ~14B–32B, not 70B)
- [ ] Confirm Ollama can serve the chosen models: `ollama list`

---

## M1 — Vertical slice

### 1. Scaffold

- [ ] `pyproject.toml` — deps: `langgraph`, `langchain`, `langchain-ollama`, `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `websockets`, `python-dotenv`
- [ ] Dev deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy`
- [ ] `uv sync` — lockfile committed
- [ ] `.gitignore` — `company_config.json`, `.env`, `__pycache__/`, `node_modules/`, `dist/`, `.venv/`, `qdrant_storage/`
- [ ] `.env.example` — `OLLAMA_BASE_URL`, `QDRANT_URL`, `LANGSMITH_API_KEY`
- [ ] `docker-compose.yml` — Qdrant service (Ollama on host or containerized)
- [ ] `ruff.toml` / `[tool.ruff]` + `[tool.mypy]` config
- [ ] Package dirs with `__init__.py`: `backend/{config,graph,graph/tiers,graph/middleware,api}`

### 2. Config layer

- [ ] `backend/config/schema.py` — Pydantic models:
  - [ ] `CompanyInfo` (name, domain, website, support_scope)
  - [ ] `Persona` (name, title, theme)
  - [ ] `PersonaSet` (front_desk, manager, vice_president, ceo)
  - [ ] `ModelSet` (one model id per tier)
  - [ ] `KnowledgeConfig` (documents[], crawl_urls[], qdrant_collection)
  - [ ] `MCPServerConfig` (name, transport, command/args **or** url, tiers[])
  - [ ] `EscalationConfig` (require_user_consent, max_attempts_per_tier, human_admin)
  - [ ] `CompanyConfig` root model
- [ ] Validator: `transport: stdio` requires `command`; `transport: http` requires `url`
- [ ] Validator: **stdio binary allowlist** — `{uvx, npx, docker}` only, `ValueError` otherwise
- [ ] Validator: every entry in `tiers[]` is a known tier name
- [ ] `backend/config/loader.py` — load, validate, cache as a module singleton
- [ ] `company_config.example.json` — the full README example, committed
- [ ] Test: valid config parses; `command: "bash"` raises; unknown tier raises

### 3. ⭐ Handoff protocol — *write first*

- [ ] `backend/graph/handoff.py`
- [ ] `AttemptedAction` model (tier, action, outcome)
- [ ] `HandoffPacket` model — all README fields, with `max_length` on every list
- [ ] `redact(text) -> (text, bool)` — regex for email / phone / card / SSN-shaped strings
- [ ] `summarize_for_handoff(state, from_tier, to_tier)` — structured-output LLM call
  - [ ] Takes the **incoming packet** as well as the transcript, so facts accumulate
  - [ ] Populates `ruled_out` from failed attempts — this is what stops re-litigation
  - [ ] Runs redaction before returning; sets `pii_redacted`
- [ ] Token-budget check → re-summarize if the packet exceeds the cap
- [ ] Test: two sequential handoffs accumulate facts rather than reset
- [ ] Test: packet respects size cap under a long synthetic transcript
- [ ] Test: emails/phones in the transcript do not survive into the packet

### 4. ⭐ Graph state + tier factory — *write second*

- [ ] `backend/graph/state.py` — `CoCState` TypedDict: `messages`, `current_tier`, `packet`, `attempt_count`, `pending_escalation`, `session_id`, `ticket_id`
- [ ] `backend/graph/tiers/base.py` — `build_tier(persona, model, tools, prompt_template) -> CompiledGraph`
  - [ ] Agent node (bind tools; **empty list stays empty** — no filtering layer)
  - [ ] Tool node (skipped entirely when the tool list is empty)
  - [ ] Structured output: `can_resolve: bool`, `escalation_reason: str | None`, `needs_context: str | None`
  - [ ] Self-introduction on first turn after a tier change
  - [ ] Attempt counter increments per unresolved turn
- [ ] Prompt template renders persona name/title from config — nothing hardcoded

### 5. Tier definitions

- [ ] `tiers/front_desk.py` — **empty tool list**, guardrail hook point, triage prompt
- [ ] `tiers/manager.py` — stub tools (`lookup_order`, `check_policy`) returning fake data
- [ ] `tiers/vice_president.py` — Manager stubs + a stub external tool
- [ ] `tiers/ceo.py` — all stubs + a stub `notify_human`
- [ ] Test: Front Desk's bound tool list is empty (regression guard on the security property)

### 6. HITL middleware

- [ ] `backend/graph/middleware/hitl.py`
- [ ] `request_escalation_consent(from_tier, to_tier, reason)` — `interrupt()`, returns bool
- [ ] `request_context(question)` — `interrupt()`, returns the user's answer
- [ ] **Conditional**: no interrupt fires when the agent needs nothing
- [ ] Wire `MemorySaver` checkpointer into graph compilation
- [ ] Test: resume after interrupt restores state correctly
- [ ] Test: a turn needing no context runs start-to-finish with zero interrupts

### 7. Supervisor

- [ ] `backend/graph/supervisor.py` — build the parent graph, mount four tier subgraphs
- [ ] `classify_user_intent()` — structured output `wants_escalation: bool` (not keyword matching)
- [ ] Routing: user-initiated escalation **skips** the consent gate
- [ ] Routing: agent-initiated escalation **requires** consent when `require_user_consent`
- [ ] Enforce `max_attempts_per_tier`
- [ ] On approved escalation: summarize → advance tier → emit `tier_change`
- [ ] **Tiers cannot self-promote** — only the supervisor writes `current_tier`
- [ ] **No auto-descalation** — assert `current_tier` is monotonically non-decreasing
- [ ] At CEO with nowhere to go → route to human escalation, keep session live
- [ ] Test: full four-hop escalation path
- [ ] Test: declined consent leaves the tier unchanged

### 8. API

- [ ] `backend/api/main.py` — FastAPI app, CORS for the Vite dev origin
- [ ] `GET /api/config` — personas + themes for the frontend (no secrets)
- [ ] `WS /ws/chat/{session_id}` — bidirectional
- [ ] Outbound event types: `token`, `agent_intro`, `tier_change`, `escalation_prompt`, `context_request`, `human_escalation`, `error`
- [ ] Inbound: `user_message`, `escalation_response`, `context_response`
- [ ] Stream tokens via `astream_events`
- [ ] Resume from checkpoint on reconnect with the same `session_id`
- [ ] Manual check: `websocat` or a scratch script drives a full escalation

### 9. Frontend

- [ ] `npm create vite@latest frontend -- --template react-ts`
- [ ] Tailwind, Zustand, Framer Motion
- [ ] `src/themes/index.ts` — theme per tier (`slate`, `amber`, `indigo`, `obsidian`), keyed off config
- [ ] `src/hooks/useWebSocket.ts` — connect, reconnect w/ backoff, typed event dispatch
- [ ] `src/hooks/useEscalation.ts` — tier state + transition orchestration
- [ ] `src/store/chat.ts` — messages, current tier, pending prompt
- [ ] `components/Chat/MessageList.tsx`, `MessageInput.tsx`, `AgentHeader.tsx`
- [ ] `components/Chat/TierTransition.tsx` — Framer Motion divider + theme crossfade
- [ ] `components/Chat/EscalationPrompt.tsx` — inline Yes/No, **not** a modal
- [ ] `components/Chat/ContextRequest.tsx` — inline input, **not** a modal
- [ ] Token streaming renders incrementally
- [ ] Theme applied via CSS custom properties on a root wrapper
- [ ] Reconnect restores the conversation and any pending interrupt

### 10. M1 verification

- [ ] Ask an in-scope question → answered at Front Desk, no escalation
- [ ] Ask an out-of-scope question → consent prompt appears
- [ ] Decline → stays at Front Desk, conversation continues
- [ ] Accept → UI transitions, Dwight introduces himself by name
- [ ] Dwight references prior attempts without you repeating them
- [ ] Inspect the `HandoffPacket`: `ruled_out` and `verified_facts` populated
- [ ] "I want to talk to upper management" → immediate escalation, no consent prompt
- [ ] Escalate all the way to CEO; each tier introduces itself
- [ ] Refresh the browser mid-interrupt → session resumes at the interrupt
- [ ] A simple follow-up at CEO tier is answered at CEO tier (no descalation)
- [ ] Front Desk tool registry empty; prompt-injected tool call fails

---

## M2 — Manager: RAG + local tools

- [ ] Add `qdrant-client`, `pypdf`, `beautifulsoup4`, `httpx`, `langchain-text-splitters`
- [ ] `backend/rag/ingest.py` — loaders for PDF, Markdown, plain text
- [ ] Web crawler over `knowledge.crawl_urls`, domain-restricted
- [ ] Chunking with overlap; source metadata retained per chunk
- [ ] Embeddings via Ollama `nomic-embed-text`
- [ ] Upsert to Qdrant; **content-hash IDs** so re-runs are idempotent
- [ ] CLI: `python -m backend.rag.ingest --config company_config.json`
- [ ] `backend/rag/retriever.py` — hybrid search, payload filtering, scored results
- [ ] Tool `rag_search(query)` → passages **with citations**
- [ ] Tool `scrape_url(url)` → allowlisted domains only
- [ ] Sandbox tool `run_code(snippet)` — Docker exec, no network, read-only rootfs, non-root, CPU/mem/timeout caps
- [ ] Swap Manager stubs for the real tools
- [ ] Structured Manager output so the CEO tier can consume typed data
- [ ] Verify: a PDF-only fact is answered with a citation; Front Desk fails the same question

---

## M3 — VP + security hardening

- [ ] Add `langchain-mcp-adapters`, `mcp`
- [ ] `backend/mcp/internal_server.py` — expose first-party tools over MCP
- [ ] `backend/mcp/registry.py` — spawn stdio subprocesses / open HTTP connections at startup
- [ ] Inject each server's tools into exactly the tiers in its `tiers[]` array
- [ ] Graceful shutdown of every spawned subprocess
- [ ] `backend/mcp/sandbox.py` — **allowlist enforced at spawn**, not just at parse
- [ ] Docker isolation: non-root, `--read-only`, `--cap-drop=ALL`, explicit mounts, egress restricted
- [ ] Resource limits: CPU, memory, PID count, wall clock
- [ ] Async tool fan-out with `asyncio.gather` in the VP loop
- [ ] Wire one real external MCP server (e.g. web search) end-to-end
- [ ] Verify: `command: "bash"` rejected before any spawn
- [ ] Verify: `docker inspect` on a live MCP container shows non-root + read-only rootfs
- [ ] Verify: VP resolves a question needing live web search

---

## M4 — CEO tier

- [ ] Evaluator–optimizer loop in `tiers/ceo.py`
- [ ] Evaluator is a **separate** structured-output call with explicit pass/fail criteria
- [ ] Bound by max iterations **and** token budget
- [ ] `backend/notifications/email.py` — SMTP to `human_admin.email`, includes the handoff packet
- [ ] `backend/notifications/push.py` — Web Push to `human_admin.push_topic`
- [ ] `backend/notifications/scheduling.py` — surface `scheduling_link` to the customer
- [ ] Tool `escalate_to_human(reason, urgency)` wired to all three channels
- [ ] Emit `human_escalation` event; frontend renders a status banner
- [ ] **Session stays live** after human escalation — CEO keeps answering
- [ ] Verify: exhaust CEO tooling → email arrives → follow-up still answered in-session

---

## M5 — Guardrails, observability, polish

- [ ] `middleware/guardrails.py` — input: prompt injection, PII, abuse, scope check
- [ ] Output guardrails at CEO: hallucinated commitments, internal leakage, unsafe advice
- [ ] Guardrail failures produce a graceful user-facing message, never a stack trace
- [ ] LangSmith / OTel tracing — **one trace per ticket**, spans crossing tier boundaries
- [ ] Trace attributes: tier, persona, model, tool calls, escalation reason
- [ ] Config hot reload without a restart
- [ ] Analytics: escalation rate, resolution-per-tier, time-to-resolution
- [ ] Admin view (or logged summary) surfacing those metrics
- [ ] pytest suite green: handoff, routing, allowlist, guardrails
- [ ] Vitest: escalation UI transition renders and themes swap
- [ ] `ruff check` and `mypy` clean
- [ ] README "Getting started" verified from a clean clone; drop the early-development banner
- [ ] Roadmap checkboxes in README updated to match reality

---

## Invariants — re-check after any refactor

These are the properties that make the design what it is. Each has a test; keep them passing.

- [ ] Front Desk's tool registry is **empty**, not filtered
- [ ] Only the supervisor writes `current_tier`
- [ ] `current_tier` never decreases within a session
- [ ] Tiers receive a `HandoffPacket`, never a raw transcript
- [ ] No stdio process spawns from a binary outside `{uvx, npx, docker}`
- [ ] HITL context requests are conditional — zero interrupts when nothing is needed
- [ ] The session survives human escalation
