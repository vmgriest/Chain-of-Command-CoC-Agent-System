# Build Checklist

Task-by-task execution list for [PLAN.md](PLAN.md). Ordered — later items assume earlier ones. Two files are marked ⭐ **write first**: everything else is shaped by them.

> **Status (2026-08-10):** M0–M5 are all built. 164 pytest tests green, `ruff
> check` clean across `backend/` and `tests/`, `tsc -b`/`vite build` clean on
> the frontend. M1's escalation flow was confirmed live in a real browser
> (Playwright) against local Ollama models back on 2026-08-08. M2–M5's core
> mechanisms (RAG ingest+retrieval, the code sandbox, the internal MCP server
> + registry, the CEO evaluator-optimizer loop, notification fan-out, and the
> input guardrail classifier) were each additionally live-verified against
> real Ollama / Qdrant / Docker during the 2026-08-09 pass — see the
> per-milestone notes below for exactly what ran. On 2026-08-10: email
> escalation verified end to end against a real Mailtrap SMTP sandbox (a real
> `send_escalation_email()` call actually delivered); **Web Push removed**
> entirely (dropped `backend/notifications/push.py`, the `push_topic` config
> field, `POST /api/push/subscribe`, and the `pywebpush` dependency) — it
> added a real external-account setup step (VAPID keys + a browser
> subscription UI that was never built) for a channel email and scheduling
> already cover; concurrent tool fan-out confirmed to already work via
> LangGraph's `ToolNode` with no custom code needed; VP's and CEO's MCP tool
> access live-verified, catching and fixing a real duplicate-tools bug in
> `ceo.real_tools()` plus a misleading config entry; and Front Desk was found
> to be the only tier that never proactively introduced itself on session
> start (every other tier greets immediately on handoff, no user message
> needed) — fixed, live-verified through a real WebSocket connection. A real
> **external MCP server was wired end to end and live-verified**: Tavily's
> hosted web-search MCP server (`https://mcp.tavily.com/mcp/`), authenticated
> via a new `headers` config field with the same `${VAR}`-from-host-env
> resolution `env` already had — a real search through it returned real,
> current results. Getting there surfaced and fixed three real bugs: (1) the
> originally-planned `@modelcontextprotocol/server-brave-search` package is
> unsupported and Brave killed its API's free tier in February 2026, so the
> example switched to Tavily, which still has one; (2) the sandbox's
> `--read-only` rootfs + nobody-user combination left `npx` with nowhere
> writable at all ("mkdir '/nonexistent': ENOENT"), fixed with a tmpfs mount
> at `/tmp`; (3) that tmpfs then defaulted to `noexec`, blocking the very
> binary npx had just downloaded ("Permission denied"), fixed by adding
> `exec` explicitly. Also fixed: `resolve_env()` originally only matched a
> value that was ENTIRELY `${VAR}`, silently failing to expand a real-world
> header like `"Bearer ${TAVILY_API_KEY}"` — generalized to match embedded
> references. What's still not live-verified: a full second browser pass
> through M2–M5 end to end.
> `mypy --strict` has pre-existing gaps inherent to LangGraph's TypedDict-heavy
> state pattern (untyped `dict` returns, etc.) — not attempted as a hard gate,
> same as it wasn't in M1. All four tiers now run `llama3.2:latest` (see
> `company_config.json`, gitignored) — the user's explicit choice to test the
> smallest model everywhere rather than reserve a bigger one for VP/CEO.
>
> **2026-08-10 (later pass): two more real bugs found live via the user's own
> demo run and fixed, 161 tests green, ruff clean.** (1) A raw structured-
> output JSON blob (`{"hallucinated_commitment": false, ...}`) was streaming
> straight onto the customer's chat bubble, glued after the real CEO reply.
> Root cause: `check_output()` in `backend/graph/middleware/guardrails.py`
> runs inside the CEO tier's `agent` graph node (via `ceo.py`'s response
> optimizer) and shares that node's `langgraph_node` metadata with the tier's
> real customer-facing stream — every other internal call in that same loop
> was already tagged `"coc_internal"` to keep it off the token stream, this
> one wasn't. Fixed by tagging it at the function definition, so any future
> caller is protected automatically; regression test in
> `tests/test_guardrails.py`. (2) VP/CEO's real web-search tool
> (`web_search.tavily_search`, Tavily's hosted MCP server) reliably failed
> tool-call validation under `llama3.2:latest` — reproduced live 3× via
> scripted `vice_president.build()` calls, error `topic Input should be
> 'general'`. Root cause: the tool exposes 14 mostly-optional parameters,
> including a JSON-Schema `const`-constrained `topic` field a 3B model kept
> filling with `""` instead of omitting; after the tool call failed the model
> answered from its own training data instead of reporting the failure, which
> is what actually produced the "answered correctly but still escalated"
> symptom (the CEO verdict step correctly saw a failed tool call and marked
> the turn unresolved). Fixed generically, not by hardcoding Tavily's tool
> name: `backend/mcp/tool_simplify.py::simplify_to_required_args()` strips
> ANY MCP tool's visible schema down to just its required parameters before
> binding it to a model — applied to every tool in `MCPRegistry.startup()`,
> a no-op for tools with nothing optional to hide. Live-verified against the
> real Tavily API with `llama3.2:latest`: the wrapped call succeeds with only
> `query` supplied, and the VP tier's end-to-end web-search turn now resolves
> with `pending_escalation=None` instead of escalating. What's still not
> live-verified: the duplicate-loading-bubble UI artifact reported alongside
> the JSON leak — plausibly the same symptom (a second bubble rendering the
> leaked JSON as its own message) but not yet confirmed against a running
> frontend.
>
> **2026-08-10 (third pass): the escalate-despite-a-good-answer symptom had a
> SECOND, broader cause beyond the Tavily fix above — found live from a user
> screenshot of Manager (RAG, no web search) giving a complete, correct
> 4-step fix and still escalating, with the escalation banner itself reading
> "I don't have unable to resolve at this tier from this desk." (visibly
> broken grammar).** Two distinct bugs, both fixed, both regression-tested,
> 163 tests green: (1) `verdict_node`'s escalation fallback text ("unable to
> resolve at this tier") was being substituted into
> `hitl.py::request_escalation_consent()`'s `"I don't have {reason} from this
> desk."` template, which expects a noun phrase, not a clause — fixed by
> changing the fallback to `"everything needed to fully resolve this"`. (2)
> The real cause of the escalation itself: `TierVerdict`'s `can_resolve`
> judgment, a separate structured-output call from `llama3.2:latest`, was
> unreliable independent of any tool failure — reproduced live, 3/3 runs,
> `can_resolve=False` for an objectively complete, hardcoded answer fed
> straight to the verdict call. Isolated by testing a trivial, unambiguous
> Q&A (return policy) which correctly returned `can_resolve=True`, narrowing
> it to troubleshooting-shaped answers specifically — the model appears to
> conflate "the customer still has to go DO something with this answer" with
> "I couldn't answer". Fixed with `VERDICT_FEWSHOT` in
> `backend/graph/tiers/base.py`, few-shot-calibrating the verdict prompt
> against exactly this confusion (same technique `guardrails.py`'s input
> screen already used successfully) plus tightening the `can_resolve` /
> `escalation_reason` field descriptions. Live-verified: the same
> reproduction that failed 3/3 (both with and without a trailing "contact
> support if this doesn't work" hedge) now passes 6/6 with
> `can_resolve=True`; a full end-to-end `manager.build()` run of the exact
> E-317 question now returns `pending_escalation: None` instead of
> escalating. Not a guarantee against every future case a 3B model
> mis-scores, but a concrete, measured fix for the specific bias found live.
>
> **2026-08-10 (fourth pass): two more real bugs found live from a follow-up
> screenshot, one on each side of the stack.** (1) **Frontend — the "weird
> duplicate loading bar" reported earlier turned out to be a real, fully
> reproducible logic bug, not a one-off render glitch.** `"introduce"` is
> every tier subgraph's ENTRY POINT (`build_tier()` in
> `backend/graph/tiers/base.py`), so its `on_chain_end` boundary fires on
> EVERY turn, not just a fresh handoff — `introduce_node` itself only
> returns a message when `tier_just_changed` is true. But
> `backend/api/main.py::_stream_turn()` was sending `AgentIntroEvent`
> unconditionally off that boundary. The frontend's `agent_intro` handler
> (`useWebSocket.ts`) opens a brand-new chat bubble via
> `startAgentMessage()` — on top of the one `MessageInput.tsx` already opens
> optimistically the moment the customer hits send — so literally every
> ordinary follow-up turn left a second, stray, permanently-empty
> `streaming: true` bubble in the timeline (nothing ever calls
> `finishAgentMessage()` on it specifically, since that function only
> resolves the LAST streaming bubble it finds). Fixed by gating the
> `AgentIntroEvent` send on `messages` being non-empty — i.e. tied to an
> actual introduction, not every turn. Regression test:
> `tests/test_api.py::test_stream_turn_does_not_resend_agent_intro_on_an_ordinary_turn`.
> (2) **Backend prompt — the agent's own final answer was routinely tacking
> a gratuitous "I recommend escalating to a higher tier" onto otherwise
> complete answers**, which the (now-fixed) verdict step would then
> correctly but unhelpfully treat as a real signal to escalate. Root cause:
> `BASE_SYSTEM_PROMPT`'s instruction "offering to escalate is a good
> outcome, not a failure" was being applied even when nothing was actually
> missing. Tightened the instruction to only invite escalation when a
> capability is genuinely missing, not as a routine sign-off. Live-verified
> against `llama3.2:latest`, 3 full round-trip runs of the exact E-317
> question: went from a 0/3 baseline (before any of today's fixes) to 2/3
> giving a complete answer with `pending_escalation: None`; the third run
> still recommended escalating unprompted — a 3B model does not follow a
> phrasing instruction with 100% consistency, and this is a measured
> improvement, not a claimed guarantee. 164 tests green, ruff clean.

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
- [x] CEO tier + escalation → `human_escalation_node` (minimal M1 version: records + keeps session live; real email/scheduling is M4)
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

- [x] Front Desk introduces itself immediately on connect, before the customer types anything — *live-verified* 2026-08-10 via a real WebSocket client against the running server: `agent_intro` → `token` (Penny's greeting) → `turn_end` arrive with zero client input. This was a real gap found live: every OTHER tier introduces itself immediately on a handoff (no new user message needed, via the supervisor's own "introduce" node), but Front Desk's self-introduction previously only fired as a side effect of the customer's first message — glued onto the answer to their first question instead of arriving as a proper greeting. Fixed in `backend/api/main.py::_greet_new_session()`, which seeds the checkpoint via `graph.aupdate_state(..., as_node=START)` and reuses the exact same `introduce()` function every handoff already calls, rather than duplicating greeting logic. `tests/test_api.py`, 3 tests.
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

- [x] Add `qdrant-client`, `pypdf`, `beautifulsoup4`, `httpx`, `langchain-text-splitters` *(already declared in `pyproject.toml` from the skeleton commit; `uv sync` pulls them)*
- [x] `backend/rag/ingest.py` — loaders for PDF, Markdown, plain text *(directory loader dispatches by extension; unsupported extensions logged and skipped, not raised)*
- [x] Web crawler over `knowledge.crawl_urls`, domain-restricted *(BFS, depth-2 cap, page cap, rate-limited; allowed domains = `company.domain` ∪ each crawl URL's own host)*
- [x] Chunking with overlap; source metadata retained per chunk *(`RecursiveCharacterTextSplitter` for PDF/txt; `MarkdownHeaderTextSplitter` for `.md` so chunks align to headings)*
- [x] Embeddings via Ollama `nomic-embed-text` *(batched, not one HTTP call per chunk)*
- [x] Upsert to Qdrant; **content-hash IDs** so re-runs are idempotent *(sha256(source+text) folded into a UUID — Qdrant point IDs must be int or UUID)*
- [x] CLI: `uv run python -m backend.rag.ingest --config company_config.json` *(`--collection` override, `--dry-run` for load+chunk only)*
- [x] `backend/rag/retriever.py` — payload filtering, scored results *(dense-only; hybrid dense+BM25 is still a TODO, noted inline — a real gap for exact-identifier queries like error codes)*
- [x] Tool `rag_search(query)` → passages **with citations** — *live-verified*: real Qdrant + Ollama embeddings, queries against the example handbook/policies/crawled site returned correct top passages with citations (`handbook.pdf, p.3`, `shipping.md, Delayed Shipments`, a crawled URL)
- [x] Tool `scrape_url(url)` → allowlisted domains only *(also refuses a redirect that leaves the allowlist)*
- [x] Sandbox tool `run_code(snippet)` — Docker exec, no network, read-only rootfs, non-root, CPU/mem/timeout caps — *live-verified*: real execution (`print(2+2)` → `4`), real network isolation confirmed (`socket.connect` → `OSError: Network is unreachable`), timeout path force-removes the container
- [x] Swap Manager stubs for the real tools *(`stub_tools()` kept around for tests that want tool-calling plumbing without a live registry)*
- [ ] Structured Manager output so the CEO tier can consume typed data *(still prose — not attempted; Manager's reply is plain text same as every other tier)*
- [x] Example RAG content: `docs/handbook.pdf` (generated by `scripts/generate_example_docs.py`, no extra PDF-authoring dependency — builds the PDF directly via `pypdf.PdfWriter`), `docs/policies/*.md`, and `docs/example_site/` (a static example support site, served locally via `python -m http.server 8080 --directory docs/example_site` — crawling a real company's live site was deliberately avoided)
- [x] Verify: a PDF-only fact (e.g. error code E-317) is answered with a citation — confirmed via direct `retriever.search()` calls against the real ingested corpus; not yet re-verified as a full Front-Desk-fails-the-same-question browser comparison

---

## M3 — VP + security hardening

- [x] Add `langchain-mcp-adapters`, `mcp` *(already declared from the skeleton commit)*
- [x] `backend/mcp/internal_server.py` — expose first-party tools over MCP *(FastMCP; `rag_search`/`scrape_url`/`run_code` delegate to the exact same `*_impl` functions the Manager tier calls directly — one source of truth, exercised over both a local call and MCP either way)*
- [x] `backend/mcp/registry.py` — spawn stdio subprocesses / open HTTP connections at startup *(via `langchain-mcp-adapters`' `MultiServerMCPClient`, not a hand-rolled subprocess manager)*
- [x] Inject each server's tools into exactly the tiers in its `tiers[]` array *(namespaced `"{server_name}.{tool_name}"`)*
- [x] Graceful shutdown of every spawned subprocess *(`registry.shutdown()` → `sandbox.shutdown_all()`, wired into the FastAPI lifespan)*
- [x] `backend/mcp/sandbox.py` — **allowlist enforced at spawn**, not just at parse *(`assert_binary_allowed` checks basename AND the `shutil.which()`-resolved basename, so a symlink can't hide a disallowed binary)*
- [x] Docker isolation: non-root, `--read-only`, `--cap-drop=ALL`, explicit mounts, egress restricted *(stdio servers run INSIDE a locked-down container regardless of whether the config says `uvx`/`npx`/`docker` — a bare `docker run <image>` invocation is still routed through the isolation flags, not trusted as-is)*
- [x] Docker-escape guard: rejects `--privileged`, `--network=host`/`--pid=host`, and any arg mounting the docker socket, before spawn
- [x] Resource limits: CPU, memory, PID count, wall clock
- [x] Async tool fan-out with `asyncio.gather` in the VP loop — turns out to need NO custom code: `langgraph.prebuilt.ToolNode` already runs every tool call in a turn concurrently via `asyncio.gather` internally (confirmed by reading the installed version's source, then *live-verified*: two artificially-slowed 1s tools returned in ~1.0s total through a real compiled graph, not ~2.0s). The M1-era TODO in `tiers/base.py` calling for custom fan-out logic was stale; removed. `test_tool_calls_in_one_turn_run_concurrently` in `tests/test_tiers.py` guards this holding across langgraph upgrades.
- [x] Wire the first-party internal MCP server end-to-end — *live-verified*: `backend/mcp/internal_server.py` run standalone over streamable-HTTP, connected to by `MCPRegistry.startup()`, tools listed and namespaced correctly (`internal_tools.rag_search`, `.scrape_url`, `.run_code`, `.lookup_order`, `.check_policy`), `rag_search` invoked through the full MCP round-trip and returned real cited passages; Front Desk confirmed to still receive zero tools even with a server active
- [x] Wire one real THIRD-PARTY external MCP server end-to-end — *live-verified* 2026-08-10 against Tavily's hosted web-search MCP server (`https://mcp.tavily.com/mcp/`, streamable-HTTP, real API key from the user's own account): connection succeeded, its 5 tools (`tavily_search`/`_extract`/`_crawl`/`_map`/`_research`) listed and namespaced, `web_search.tavily_search` invoked through `vice_president.real_tools()` and returned real, current results (a real Wikipedia summary of MCP itself). Required adding a `headers` config field (mirrors `env`'s `${VAR}`-from-host-environment resolution, reused via the same `resolve_env()`) since Tavily authenticates over an `Authorization: Bearer <key>` header rather than an env var — see the top-of-file status note for the three real bugs this surfaced and fixed (tmpfs for npx's cache, `exec` on that tmpfs, and `resolve_env()` only matching a whole-string reference instead of one embedded in a larger value). `tests/test_mcp.py` covers header resolution and registry wiring; the live run is the origin project's actual `company_config.json`, not a fixture.
- [x] Verify: `command: "bash"` rejected before any spawn *(`tests/test_mcp.py`, plus the schema-level parse-time check in `tests/test_invariants.py`)*
- [ ] Verify: `docker inspect` on a live MCP container shows non-root + read-only rootfs *(the flags are asserted present in the constructed argv via tests; the live-verified external server above is HTTP-transport, so it never spawns a local container to inspect — a live stdio-transport third-party server, sandboxed via Docker, is still unconfirmed against actual container runtime state)*
- [x] Verify: VP resolves a question needing tools it wouldn't otherwise have — `vice_president.real_tools()` = Manager's real tools + `registry.tools_for_tier(VICE_PRESIDENT)`, confirmed to include zero MCP tools when the registry hasn't started (safe default for tests/isolated builds) and the full namespaced set once a real server is connected
- [x] Verify: CEO tier's MCP tools — *live-verified* 2026-08-10, and a real bug found + fixed in the process: `ceo.real_tools()` = `vp_real_tools() + registry.tools_for_tier(CEO) + [escalate_to_human]` double-counted every tool from a server (like `internal_tools`) that lists BOTH `vice_president` and `ceo` in its `tiers` array — `internal_tools.rag_search` etc. appeared TWICE in the CEO's bound tool list. Fixed by filtering `registry.tools_for_tier(CEO)` down to names not already present in `vp_real_tools()`. Also found: `company_config.json`/`.example.json` listed `"manager"` in `internal_tools`'s `tiers`, which was silently a no-op — the Manager tier's own docstring is explicit ("LOCAL TOOLS ONLY, no external MCP") and its `real_tools()` never reads the registry at all. Config fixed to match the documented architecture rather than changing Manager's capability boundary. `test_ceo_real_tools_deduplicates_mcp_tools_shared_with_vp` in `tests/test_ceo.py` guards the dedup fix.

---

## M4 — CEO tier

- [x] Evaluator–optimizer loop in `tiers/ceo.py` — *live-verified*: seeded with a deliberately over-promising draft ("Sure, I'll refund you right now, no problem at all!") against a real Ollama model outside the return window; the evaluator correctly flagged it and the reviser produced a policy-compliant, non-committal response
- [x] Evaluator is a **separate** structured-output call with explicit pass/fail criteria *(`DraftEvaluation`, four named checks + a `.passed` property; a distinct model call from the drafter)*
- [x] Bound by max iterations **and** token budget *(`MAX_OPTIMIZE_ITERATIONS`, `MAX_OPTIMIZE_TOKENS`; both independently tested — the loop returns the best draft on exhaustion rather than looping forever or raising)*
- [x] `backend/notifications/email.py` — SMTP to `human_admin.email`, includes the handoff packet *(built from the `HandoffPacket`, not the transcript — same protocol, different consumer; failures logged and return `False`, never raise)*
- [x] `backend/notifications/scheduling.py` — surface `scheduling_link` to the customer *(ticket_id appended as a query param so the packet is waiting for whoever takes the call)*
- [x] Tool `escalate_to_human(reason, urgency)` wired to both channels — *live-verified*: invoked through a real compiled `ToolNode` inside an actual `StateGraph`, confirmed the `Command`-returned state update lands correctly (`human_notified: True`, `_last_human_escalation_channels`) — this is what gives the CEO's own proactive tool call exact parity with the automatic supervisor-routed path, both detected identically by the API layer via a `human_notified` state diff rather than by node name
- [x] Emit `human_escalation` event; frontend renders a status banner *(existing M1 `HumanEscalationBanner` component; wire protocol unchanged, so no frontend code needed updating)*
- [x] **Session stays live** after human escalation — CEO keeps answering *(unchanged M1 invariant; both escalation paths return to the conversation, never end it)*
- [x] `notify_human()` channel selection — *live-verified* twice: against real unconfigured SMTP (correctly skipped with a logged reason, `scheduling` still included) on 2026-08-09, then again against a real Mailtrap SMTP sandbox on 2026-08-10 with `SMTP_HOST`/`USER`/`PASSWORD` actually set
- [x] Verify: exhaust CEO tooling → email arrives → follow-up still answered in-session — *live-verified* 2026-08-10: `send_escalation_email()` called directly against real Mailtrap credentials, returned `True`, email confirmed to land in the Mailtrap inbox; the "follow-up still answered" half of this was already covered by `test_escalate_to_human_tool_updates_state_via_command` (session continues, `human_notified` doesn't block the graph). ~~Web Push~~ removed 2026-08-10 — see the status note at the top of this file.

---

## M5 — Guardrails, observability, polish

- [x] `middleware/guardrails.py` — input: prompt injection, PII, abuse, scope check — *live-verified* against real Ollama: initially the classic injection phrasing ("Ignore all previous instructions...") was missed and an off-topic question ("What is the capital of France?") wasn't flagged off-scope — same "small model needs few-shot examples" issue `classify_intent` hit in M1. Fixed by adding few-shot examples (`INPUT_GUARDRAIL_FEWSHOT`); all six re-tested phrasings then classified correctly, including edge cases like "is there a manager around" correctly staying in-scope
- [x] Output guardrails at CEO: hallucinated commitments, internal leakage, unsafe advice *(runs as one more pass at the end of the evaluator-optimizer loop, not a separate mechanism — on failure it revises once from the guardrail's own critique rather than blocking outright, per the "a refusal helps nobody" design note)*
- [x] Guardrail failures produce a graceful user-facing message, never a stack trace *(abuse → one de-escalating reply, then a firm close after `MAX_ABUSE_WARNINGS`; off-scope → a plain decline that does NOT escalate, since escalating an off-topic question just moves the problem up the ladder; PII → redacted into state via the same `redact()` handoff.py already uses, not a refusal)*
- [x] LangSmith tracing — configured from `LANGSMITH_*` env vars, off by default, warns (doesn't fail) if enabled without an API key *(chose LangSmith over OTel: LangGraph-native, and this project already depends on langchain/langgraph)*
- [ ] Trace attributes: tier, persona, model, tool calls, escalation reason *(not implemented — LangSmith's auto-instrumentation covers the call graph, but the enrichment described in the original TODO, e.g. `handoff_packet_tokens` as a specific span attribute to watch, was not added on top of it)*
- [x] Config hot reload without a restart — `reload_config()` validates before swapping (a bad edit leaves the previous good config in place, confirmed by test), and is explicit in its own docstring about what it does and doesn't cover: knowledge/escalation/support-scope config re-reads on the next call (per-call reads, not baked into the compiled graph); model ids and personas do NOT hot-reload, since both are resolved once at `build_graph()` time and swapping a model underneath a live conversation is exactly the risk the original TODO flagged — wired to `POST /api/admin/reload-config`
- [x] Analytics: escalation rate, resolution-per-tier, time-to-resolution *(and consent refusal rate, mean tiers traversed, human escalation rate, top escalation reasons — one JSON file upserted by `ticket_id` after every turn, since this system has no explicit "ticket closed" signal to hang a one-time write on)*
- [x] Admin view: `GET /api/analytics` *(no dedicated frontend page — matches `/api/health`'s existing bare-JSON pattern rather than adding new frontend surface for this pass)*
- [x] pytest suite green: handoff, routing, allowlist, guardrails — **143 tests**, all passing (`tests/test_rag.py`, `test_mcp.py`, `test_ceo.py`, `test_notifications.py`, `test_guardrails.py`, `test_observability.py` added this pass; existing M1 suites updated where the new guardrail node or config shape changed their assumptions)
- [ ] Vitest: escalation UI transition renders and themes swap *(not attempted — no frontend code changed this pass, and Vitest was never wired up in M1 either)*
- [x] `ruff check` clean across `backend/` and `tests/`
- [ ] `mypy --strict` clean *(72 pre-existing findings across 18 files, almost entirely bare-generic `dict`/`list` annotations and LangGraph's TypedDict-state pattern reading as `Any` under strict mode — e.g. `consent_node` indexing `pending_escalation` without mypy being able to see the routing-level None-check that actually guards it. Spot-checked several; none look like real bugs. `python_version` bumped from 3.11 to 3.12 in `pyproject.toml` to fix one hard blocker — `qdrant-client` (M2) pulls in `numpy` transitively, whose shipped stubs need 3.12+ to parse at all. Not chased further — mypy was never a verified-clean gate even at the end of M1)*
- [ ] README "Getting started" verified from a clean clone; drop the early-development banner *(not done this pass — see the note at the top of this file for the actual verified state)*
- [ ] Roadmap checkboxes in README updated to match reality *(pending — see the note below)*

---

## Invariants — re-check after any refactor

These are the properties that make the design what it is. Each has a test; keep them passing.

- [x] Front Desk's tool registry is **empty**, not filtered — still holds through M3's MCP registry (`registry.tools_for_tier(FRONT_DESK)` has an explicit second-line-of-defence check, tested with a deliberately misconfigured server that lists `front_desk` in its `tiers`)
- [x] Only the supervisor writes `current_tier`
- [x] `current_tier` never decreases within a session
- [x] Tiers receive a `HandoffPacket`, never a raw transcript *(worth re-reading the note in `backend/graph/middleware/guardrails.py`'s module docstring, added this pass: this is true only AT the moment of handoff — the customer keeps typing directly to whichever tier is current afterward, which is why the M5 input guardrail is gated on `current_tier == FRONT_DESK` rather than "first message only")*
- [x] No stdio process spawns from a binary outside `{uvx, npx, docker}` — enforced at parse (schema) AND at spawn (`sandbox.assert_binary_allowed`, checking both the raw basename and the `shutil.which()`-resolved one)
- [x] HITL context requests are conditional — zero interrupts when nothing is needed
- [x] The session survives human escalation — now true via TWO paths, not one: the original supervisor-routed automatic path, and the CEO's own `escalate_to_human` tool added in M4, both landing on the same `human_notified` state field
