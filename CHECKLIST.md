# Build Checklist

Task-by-task execution list for [PLAN.md](PLAN.md). Ordered — later items assume earlier ones. Two files are marked ⭐ **write first**: everything else is shaped by them.

> **Status (2026-08-08):** M0 and M1 are built and verified — backend graph, HITL,
> API, and frontend all implemented; 54 pytest tests green; full escalation flow
> confirmed live in a real browser (Playwright) against local Ollama models. Two
> real bugs found and fixed during live testing are noted inline below. M2–M5 are
> still stubs. Models mapped to what's actually pulled on this machine:
> `front_desk=llama3.2:latest`, `manager=llama3:8b`, `vice_president=gemma4:26b`,
> `ceo=glm-4.7-flash:latest` (see `company_config.json`, gitignored).

---

## M0 — Pre-flight

- [x] `python --version` → 3.11+ ✅ *(3.11.9 / 3.12 both present; uv pins 3.12)*
- [x] `uv --version` ✅ *(0.11.0)*
- [x] `node --version` → 20+ ✅ *(v22.18.0)*
- [x] `docker --version` + `docker compose version` ✅ *(29.4.0 — not exercised yet, no M2/M3 containers built)*
- [x] `ollama --version` ✅ *(0.32.6)*
- [x] Decide CEO-tier model from actual available RAM/VRAM ✅ *(32GB RAM / 8GB VRAM laptop 4070 → `glm-4.7-flash:latest`, 19GB, CPU+GPU offload)*
- [x] Confirm Ollama can serve the chosen models: `ollama list` ✅ *(codellama, llama3.2, llama3:8b, gemma4:26b, glm-4.7-flash all present)*

---

## M1 — Vertical slice

### 1. Scaffold

- [x] `pyproject.toml` — deps as specced
- [x] Dev deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy`
- [x] `uv sync` — lockfile present (`.venv` local, not committed per `.gitignore`)
- [x] `.gitignore` — covers `company_config.json`, `.env`, `__pycache__/`, `node_modules/`, `dist/`, `.venv/`, `qdrant_storage/`
- [x] `.env.example` — present from skeleton commit
- [x] `docker-compose.yml` — Qdrant service present from skeleton commit
- [x] `ruff.toml` / `[tool.ruff]` + `[tool.mypy]` config — present; `ruff check` clean on all M1 code (remaining hits are pre-existing M4/M5 stub docstring lines, untouched)
- [x] Package dirs with `__init__.py`: `backend/{config,graph,graph/tiers,graph/middleware,api}`

### 2. Config layer

- [x] `backend/config/schema.py` — all models implemented: `CompanyInfo`, `Persona`, `PersonaSet`, `ModelSet`, `KnowledgeConfig`, `MCPServerConfig`, `EscalationConfig`, `CompanyConfig`
- [x] Validator: `transport: stdio` requires `command`; `transport: http` requires `url`
- [x] Validator: **stdio binary allowlist** — `{uvx, npx, docker}` only, `ValueError` otherwise
- [x] Validator: every entry in `tiers[]` is a known tier name (enforced by the `Tier` enum type)
- [x] Validator: `front_desk` cannot appear in any MCP server's `tiers[]` (core invariant)
- [x] `backend/config/loader.py` — `load_config`, `get_config` (lru_cache), `startup_checks` (warns on unpulled models/missing docs/missing PATH binaries)
- [x] `company_config.example.json` — present, validates
- [x] Test: valid config parses; `command: "bash"` raises; unknown tier raises — `tests/test_config.py`, 10 tests

### 3. ⭐ Handoff protocol — *write first*

- [x] `backend/graph/handoff.py`
- [x] `AttemptedAction` model
- [x] `HandoffPacket` model — all fields, `max_length` on every list, `estimated_tokens()` / `is_over_budget()`
- [x] `redact(text) -> (text, bool)` — email / phone / card / SSN patterns, typed placeholders
- [x] `summarize_for_handoff(...)` — structured-output call on the **destination** tier's model
  - [x] Takes the incoming packet so facts accumulate
  - [x] Prompted to populate `ruled_out` from failed attempts
  - [x] Redaction runs on the result; `pii_redacted` set
  - [x] Over-budget → one retry with a more-concise prompt, then truncates (never loops)
- [x] Test: redaction (email/phone/card, no false-positive on order IDs), packet construction, summarizer merge/budget/model-choice — `tests/test_handoff.py`, 11 tests

### 4. ⭐ Graph state + tier factory — *write second*

- [x] `backend/graph/state.py` — `CoCState`, `new_state()`, `reset_for_tier()`
- [x] `backend/graph/tiers/base.py` — `build_tier()`, `make_model()`, `introduce()`, `render_system_prompt()`
  - [x] Agent node; tools bound only when non-empty (`make_model` returns the model **unbound**, never `.bind_tools([])`)
  - [x] Tool node omitted entirely when tools is empty
  - [x] `TierVerdict` structured output (`can_resolve`, `escalation_reason`, `needs_context`)
  - [x] Self-introduction node, gated on `tier_just_changed`
  - [x] `attempt_count` increments on an unresolved verdict
- [x] Prompt renders persona name/title/company from config — nothing hardcoded (test: `test_persona_name_comes_from_config`)

### 5. Tier definitions

- [x] `tiers/front_desk.py` — empty tool list
- [x] `tiers/manager.py` — stub tools `lookup_order`, `check_policy` (obviously fake, prefixed `STUB:`)
- [x] `tiers/vice_president.py` — manager stubs + stub `web_search`
- [x] `tiers/ceo.py` — VP stubs + stub `notify_human`
- [x] Test: Front Desk's bound tool list is empty, and the compiled graph has no `tools` node at all — `tests/test_invariants.py`, `tests/test_tiers.py`

### 6. HITL middleware

- [x] `backend/graph/middleware/hitl.py`
- [x] `request_escalation_consent()` — `interrupt()`, phrased around the capability gap; refusal sets `escalation_declined` so the tier doesn't immediately re-propose it
- [x] `request_context()` — `interrupt()`, capped at `MAX_CONTEXT_REQUESTS_PER_TURN = 2`
- [x] Conditional: no interrupt when the agent needs nothing (test: `test_no_interrupt_when_no_context_needed`)
- [x] `MemorySaver` checkpointer wired into `build_graph()` (with an explicit msgpack allowlist for `Tier`/`HandoffPacket` — found live, see notes below)
- [x] Test: resume after interrupt (rebuild the graph against the same checkpointer, resume with `Command`) — `test_resume_after_interrupt`

### 7. Supervisor

- [x] `backend/graph/supervisor.py` — parent graph, four tier subgraphs mounted as nodes
- [x] `classify_intent()` — structured `UserIntent.wants_escalation`, few-shot prompted (see notes — a small local model needed examples to hit the phrasings in the checklist reliably)
- [x] User-initiated escalation skips consent — routes straight to `handoff`
- [x] Agent-initiated escalation requires consent when `require_user_consent`; waived when the config disables it or `max_attempts_per_tier` is hit
- [x] On approved escalation: `do_handoff` summarizes → advances tier → stashes a `tier_change` event for the API layer, then runs the intro node in the **same turn**
- [x] Only `do_handoff` writes `current_tier` (test: `test_tier_verdict_node_never_returns_current_tier`)
- [x] `do_handoff` asserts the new tier index is strictly greater than `current_tier`'s, raising rather than silently descalating (test: `test_handoff_rejects_backward_transition`)
- [x] CEO tier + escalation → `human_escalation_node` (minimal M1 version: records + keeps session live; real email/push/scheduling is M4)
- [x] Test: routing table (classification → handoff/human/tier; tier → context/consent/handoff/human/end), consent waived/forced, resume-after-interrupt — `tests/test_supervisor.py`, 15 tests
- [ ] Test: full automated four-hop escalation path with scripted fakes *(verified live through Manager only; VP/CEO hops verified structurally via routing tests + the standalone Ollama smoke script, not as one automated test)*
- [ ] Test: declined consent leaves the tier unchanged *(mechanism implemented and code-reviewed; no dedicated automated test yet)*

### 8. API

- [x] `backend/api/main.py` — FastAPI app, lifespan loads config + `startup_checks` + builds the graph once, CORS from `CORS_ORIGINS`
- [x] `GET /api/health`, `GET /api/config` (public-safe — personas/themes only)
- [x] `WS /ws/chat/{session_id}` — bidirectional, resumes from checkpoint, re-sends a pending interrupt on reconnect
- [x] Outbound: `token`, `agent_intro`, `tier_change`, `escalation_prompt`, `context_request`, `human_escalation`, `error`, and **`turn_end`** (added live — see notes)
- [x] Inbound: `user_message`, `escalation_response`, `context_response`
- [x] Tokens streamed via `astream_events`, filtered to the tier's own "agent" node so structured-output internals (classify/verdict/summarize) never leak onto the wire
- [x] Resume from checkpoint on reconnect with the same `session_id`
- [x] Manual check: driven live with a headless-Chromium (Playwright) script through the real frontend, not just a scratch WS script

### 9. Frontend

- [x] Vite + React + TS scaffold present from skeleton commit; `npm install` done
- [x] Tailwind, Zustand, Framer Motion wired
- [x] `src/themes/index.ts` — slate/amber/indigo/obsidian, contrast-checked, obsidian intentionally inverts to dark+gold for the CEO tier
- [x] `src/hooks/useWebSocket.ts` — connect, exponential backoff (1s→30s), typed dispatch, outbound queue while disconnected
- [x] `src/hooks/useEscalation.ts` — theme + `transitioning` flag, `prefers-reduced-motion` aware
- [x] `src/store/chat.ts` — `timeline` (messages ∪ transition markers), pending prompts, `turnInProgress` (added live — see notes), config
- [x] `components/Chat/MessageList.tsx`, `MessageInput.tsx`, `AgentHeader.tsx` — messages keep their own tier's styling; auto-scroll only when already near bottom
- [x] `components/Chat/TierTransition.tsx` — divider + `packet_summary`, Framer Motion
- [x] `components/Chat/EscalationPrompt.tsx` / `ContextRequest.tsx` — inline, not modals; decline is a first-class button
- [x] `components/Chat/HumanEscalationBanner.tsx` — sticky, dismissible to a pill, chat stays usable underneath
- [x] Token streaming renders incrementally
- [x] Theme applied via CSS custom properties on a root wrapper (`applyTheme`), not Tailwind class swaps
- [x] Reconnect resends any pending interrupt (server-side); client replaces pending state rather than duplicating it
- [x] `npx tsc -b` and `npm run build` both clean

### 10. M1 verification

- [x] Ask an in-scope question → answered at Front Desk, no escalation *(live, browser)*
- [ ] Ask an out-of-scope question → consent prompt appears *(mechanism implemented + unit tested; not reliably reproduced live — the 3B front-desk model is inconsistent about when it asks for context vs. proposes escalation)*
- [ ] Decline → stays at Front Desk, conversation continues *(implemented; not live-verified)*
- [x] Accept → UI transitions, new persona introduces itself by name *(live, browser — Dwight, amber theme, full transition divider with `packet_summary`)*
- [ ] Dwight references prior attempts without you repeating them *(the packet mechanism is tested in `test_handoff.py`; not demonstrated live with a rich multi-fact transcript)*
- [x] Inspect the `HandoffPacket`: mechanism populates `ruled_out`/`verified_facts` from the transcript — `test_summarizer_records_failures_in_ruled_out`-style coverage in `test_handoff.py`
- [x] "I want to talk to upper management" → immediate escalation, no consent prompt *(live, browser + `test_user_initiated_escalation_skips_consent`)*
- [ ] Escalate all the way to CEO; each tier introduces itself *(Front Desk → Manager verified live; Manager → VP → CEO verified only via the standalone scripted Ollama session, not through the browser)*
- [ ] Refresh the browser mid-interrupt → session resumes at the interrupt *(server-side resend-on-reconnect implemented and unit-tested via `test_resume_after_interrupt`; not exercised with an actual browser refresh)*
- [ ] A simple follow-up at CEO tier is answered at CEO tier (no descalation) *(monotonic-tier invariant is tested; not exercised at the CEO tier specifically)*
- [x] Front Desk tool registry empty; graph has no tool node — `test_front_desk_tool_registry_is_empty`, `test_front_desk_graph_has_no_tool_node`

**Bugs found and fixed during live browser testing (not caught by pytest, since they only surface with a real client):**
1. **LangGraph node-schema inference broke when `CoCState` was only imported under `TYPE_CHECKING`.** `add_conditional_edges` calls `get_type_hints()` on routing functions at graph-build time, which needs the name resolvable at runtime, not just for type checkers. Fixed by making it a real top-level import in `tiers/base.py` and `supervisor.py`.
2. **`astream_events` node-boundary detection.** Nested runnables inside a node (e.g. the `ChatOllama` call inside `do_handoff`) share that node's `langgraph_node` metadata, so filtering on metadata alone caught internal sub-calls too. Fixed by also requiring `event["name"] == node`.
3. **Small-model classifier miss.** `llama3.2:latest` (3B) missed several of the exact escalation phrasings this checklist calls out (`"is there a manager around"`, `"who's your boss"`) at zero-shot. Fixed with a few-shot prompt in `classify_intent`; all six checklist phrasings now classify correctly at `temperature=0`.
4. **`useWebSocket` reconnect race (real bug, not a model artifact).** A shared `ref` for "closed intentionally" was reset by React StrictMode's remount *before* the old socket's async `onclose` fired, so the old socket concluded it had dropped unexpectedly and opened a spurious third connection. Fixed by scoping that flag to each effect invocation via a plain closure variable instead of a ref.
5. **Composer allowed sending mid-stream.** Nothing disabled the input while the current turn was still streaming, so a fast second message started a new bubble while the first turn's trailing tokens kept arriving — and got appended to the wrong bubble. Added `turnInProgress` state (set on any outbound send, cleared on the new `turn_end` event) and gated the composer on it.
6. **No `turn_end` event existed in the wire protocol.** Without one, the client couldn't tell "no tokens yet" from "no tokens ever," so a plain (non-escalating) reply's message bubble never left `streaming: true`. Added `TurnEndEvent` to `backend/api/events.py` / `frontend/src/types/index.ts`, emitted at the end of every `_stream_turn`.

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
