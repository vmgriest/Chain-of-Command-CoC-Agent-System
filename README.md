# Chain of Command (CoC) — Agent System

A multi-tier customer support chatbot where every escalation is a real handoff: the agent changes, its capabilities change, and the UI changes with it.

Instead of one omniscient assistant with every tool bolted on, CoC models a corporate ladder. The Front Desk answers from memory alone. The Department Manager gets local tools and RAG. The VP gets external MCP servers. The CEO gets everything, plus the ability to pull a human into the loop. A question only climbs as far as it needs to.

---

## Table of Contents

- [Why a chain of command](#why-a-chain-of-command)
- [The four tiers](#the-four-tiers)
- [Escalation](#escalation)
- [State Summarization & Handoff Protocol](#state-summarization--handoff-protocol)
- [Human-in-the-loop middleware](#human-in-the-loop-middleware)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Company configuration](#company-configuration)
- [Security model](#security-model)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Roadmap](#roadmap)

---

## Why a chain of command

Three problems with the single-agent support bot:

1. **Cost and latency scale with the worst case.** Every "what are your hours?" pays for the same tool-loaded, MCP-connected, 40k-token-context agent as "my enterprise SSO integration is broken." Tiering means simple questions get answered by a cheap, fast model with no tools.
2. **Blast radius.** An agent that can shell out to external MCP servers is an agent that can shell out to external MCP servers *on turn one, from an anonymous user*. Capability should be earned through escalation, not granted by default.
3. **Escalation is invisible.** Users can't tell whether they're being helped or stalled. Here, escalation is a visible event — new persona, new introduction, new UI theme. The user knows they moved up.

---

## The four tiers

Each tier runs **its own agentic loop** with its own model, prompt, tool bindings, and guardrails. Personas below are the defaults; see [Company configuration](#company-configuration) to rename them.

### 1. Front Desk — *"Penny"*

**Tools:** none.

A pure conversational agent. It answers only from what the base model was trained on — if the question is about something that shipped after the model's cutoff, it can't help, and it says so and offers to escalate. That's by design, not a bug.

- **Input guardrails** — PII scrubbing, prompt-injection detection, abuse filtering, topic scoping
- **Fast triage** — classify intent and route; most tickets die here
- **Handoffs** — hand up the ladder with a structured summary, never a raw transcript
- **Prompt chaining** — multi-step clarification before deciding it's stuck

Runs the smallest, fastest local model in the stack.

### 2. Department Manager — *"Dwight"*

**Tools:** internal only. No MCP.

The first tier that can look things up.

- **Local tool calling** — internal function tools registered in-process
- **RAG over Qdrant** — company handbooks, policy PDFs, Markdown docs, support archives
- **Web scraping** — fetch and extract from a company-approved URL allowlist
- **Code sandbox execution** — run untrusted generated code in a locked-down container
- **Structured output** — Pydantic-validated responses so downstream tiers get typed data, not prose

### 3. Vice President — *"Shiv"*

**Tools:** internal **+** external MCP.

Everything the Manager has, plus the outside world.

- **MCP (Model Context Protocol)** — external servers declared in config, connected at startup
- **Stdio transport** — local MCP servers spawned as sandboxed subprocesses
- **Asyncio execution loops** — tool calls fan out concurrently instead of serially
- **Live web search** — for anything not in the knowledge base

### 4. CEO — *configurable real name*

**Tools:** all of them, plus a human.

The last stop. The CEO re-attempts the problem from scratch with the full toolset before reaching for a person.

- **Evaluator–Optimizer loop** — draft, self-critique against the user's actual goal, revise, repeat until the evaluator passes or the budget is spent
- **Human-in-the-loop escalation** — email the admin, send a push notification, or schedule a call with the customer
- **Observability / tracing** — every tier transition, tool call, and token is traced
- **Output guardrails** — final check for hallucinated commitments, leaked internals, unsafe advice

Two behaviors that matter here:

- **The session does not end.** When the CEO emails an admin or books a call, the chat stays live. The user gets told what was done and what happens next, and can keep talking.
- **No auto-descalation.** Once at the CEO tier, a simple follow-up ("what's your refund window?") is just answered. The user is not bounced back down to the Front Desk mid-conversation.

---

## Escalation

Two paths up:

**User-initiated.** The user says some version of *"I want to talk to upper management."* Immediate, no confirmation needed. Recognized by intent classification, not keyword matching.

**Agent-initiated.** The current tier decides it can't solve the problem — missing tool, missing knowledge, low confidence, repeated failed attempts. It does **not** escalate silently. It tells the user what it's stuck on and asks:

> *"I don't have access to your billing records from this desk. Would you like me to bring in a department manager who does?"*

The human decides. Human-in-the-loop is a gate on every agent-initiated hop.

On escalation:

1. Current tier produces a **handoff packet** (below)
2. Next tier boots with that packet as its context
3. The new agent **introduces itself by name and role** — every time
4. The **frontend switches themes** — color, avatar, layout, tier badge — so escalation is unmistakable

```
┌──────────────┐   can't answer + user approves    ┌──────────────────────┐
│  Front Desk  │ ────────────────────────────────► │  Department Manager  │
│   (no tools) │                                   │   (local tools, RAG) │
└──────────────┘                                   └──────────┬───────────┘
                                                              │
                          ┌───────────────────────────────────┘
                          ▼
              ┌──────────────────────┐   still stuck    ┌───────────────────┐
              │    Vice President    │ ───────────────► │        CEO        │
              │  (internal + MCP)    │                  │  (all + human)    │
              └──────────────────────┘                  └─────────┬─────────┘
                                                                  │
                                                     email / push / schedule call
                                                                  ▼
                                                          ┌───────────────┐
                                                          │  Human Admin  │
                                                          └───────────────┘
```

---

## State Summarization & Handoff Protocol

Passing raw message history up the chain accumulates fluff. By the third hop, the CEO is reading a Front Desk agent's small talk and burning context on it.

Instead, each tier emits a **structured, validated handoff packet**:

```jsonc
{
  "ticket_id": "coc_01HX...",
  "customer_intent": "Cannot complete SSO setup; SAML assertion rejected",
  "verified_facts": [
    "Account #48812, Enterprise tier",
    "Okta as IdP, confirmed by user",
    "Error appeared after the Jan 14 rotation"
  ],
  "attempted_actions": [
    { "tier": "front_desk", "action": "walked through standard SSO checklist", "outcome": "no resolution" },
    { "tier": "manager", "action": "rag_search(sso_troubleshooting)", "outcome": "docs cover Azure AD only" }
  ],
  "ruled_out": ["expired certificate", "clock skew", "wrong ACS URL"],
  "open_questions": ["Is the customer's IdP metadata current in our directory?"],
  "sentiment": "frustrated",
  "escalation_reason": "requires external MCP access to the identity provider",
  "pii_redacted": true
}
```

Properties:

- **Typed and validated** — a Pydantic schema, not free text. Malformed packets fail loudly at the boundary.
- **Facts over transcript** — what's *known*, not what was *said*.
- **Negative results carried forward** — `ruled_out` stops each tier from re-litigating dead ends.
- **Bounded** — the packet has a size cap; summarization is enforced, not hoped for.
- **Redacted at the boundary** — PII is stripped once, on the way up, not at every tier.

The raw transcript stays available for audit and observability. It just doesn't ride along in the prompt.

---

## Human-in-the-loop middleware

Every tier's agentic loop is wrapped in middleware that can pause execution to ask the user for context the agent needs to proceed:

> *"To pull up your billing history I'll need your account number."*

Key behavior: **if no information is needed, the loop continues uninterrupted.** The middleware is a conditional interrupt, not a mandatory checkpoint — no "are you sure?" on every turn.

Implemented as LangGraph interrupts, so state is checkpointed at the pause and resumed cleanly when the user replies — including across page reloads and reconnects.

---

## Architecture

```
                          ┌─────────────────────────────────────┐
                          │   React frontend (per-tier themes)  │
                          └──────────────────┬──────────────────┘
                                             │ WebSocket / SSE
                          ┌──────────────────▼──────────────────┐
                          │      FastAPI gateway + auth         │
                          └──────────────────┬──────────────────┘
                                             │
                    ┌────────────────────────▼────────────────────────┐
                    │              LangGraph orchestrator             │
                    │  ┌───────────────────────────────────────────┐  │
                    │  │  supervisor · escalation router           │  │
                    │  │  handoff summarizer · HITL interrupts     │  │
                    │  └───────────────────────────────────────────┘  │
                    │   front_desk → manager → vp → ceo (subgraphs)   │
                    └──┬──────────────┬──────────────┬─────────────┬──┘
                       │              │              │             │
              ┌────────▼───┐  ┌───────▼──────┐  ┌────▼──────┐ ┌────▼─────────┐
              │   Ollama   │  │    Qdrant    │  │ Internal  │ │ External MCP │
              │    LLMs    │  │  vector DB   │  │    MCP    │ │  (sandboxed) │
              └────────────┘  └──────────────┘  └───────────┘ └──────────────┘
                                                                     │
                                                    ┌────────────────▼──────────────┐
                                                    │  Notifications: SMTP · push   │
                                                    │  · calendar scheduling        │
                                                    └───────────────────────────────┘
```

Each tier is a LangGraph subgraph with its own state, tool registry, and loop. The supervisor owns transitions; tiers cannot promote themselves.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | **LangGraph** | Explicit state machine, checkpointing, native interrupt support for HITL |
| Agent tooling | **LangChain** | Tool abstractions, MCP adapters, structured output |
| Models | **Ollama** | Fully local inference; per-tier model sizing (small at Front Desk, large at CEO) |
| Vector store | **Qdrant** | Hybrid search, payload filtering, self-hostable |
| Tool protocol | **MCP** | Internal server (first-party tools) + external servers (third-party) |
| API | **FastAPI** | Async-native, streams over WebSocket/SSE |
| Frontend | **React + TypeScript** | Production UI — not Gradio. Per-tier theming, streaming, escalation transitions |
| Notifications | SMTP · Web Push · calendar API | CEO-tier human escalation |
| Observability | LangSmith / OpenTelemetry | Traces spanning tier boundaries |
| Isolation | **Docker** | Sandboxed MCP subprocesses and code execution |

---

## Company configuration

The entire escalation pipeline is plug-and-play. A company drops in one `company_config.json` and gets a working support chain — **no changes to agent orchestration code**.

At startup the config module parses this file, spawns the declared stdio subprocesses and HTTP connections, and injects each tool into its designated tier.

```jsonc
{
  "company": {
    "name": "Acme Robotics",
    "domain": "acme.com",
    "website": "https://acme.com",
    "support_scope": ["orders", "returns", "hardware troubleshooting"]
  },

  "personas": {
    "front_desk":  { "name": "Penny",  "title": "Front Desk Associate", "theme": "slate" },
    "manager":     { "name": "Dwight", "title": "Support Manager",      "theme": "amber" },
    "vice_president": { "name": "Shiv", "title": "VP of Customer Success", "theme": "indigo" },
    "ceo":         { "name": "Jensen Huang", "title": "Chief Executive Officer", "theme": "obsidian" }
  },

  "models": {
    "front_desk": "llama3.2:3b",
    "manager":    "qwen2.5:14b",
    "vice_president": "qwen2.5:32b",
    "ceo":        "llama3.3:70b"
  },

  "knowledge": {
    "documents": ["./docs/handbook.pdf", "./docs/policies/"],
    "crawl_urls": ["https://acme.com/support", "https://acme.com/docs"],
    "qdrant_collection": "acme_support"
  },

  "mcp_servers": {
    "internal": [
      { "name": "orders", "transport": "stdio", "command": "uvx", "args": ["acme-orders-mcp"], "tiers": ["manager", "vice_president", "ceo"] }
    ],
    "external": [
      { "name": "web_search", "transport": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-brave-search"], "tiers": ["vice_president", "ceo"] },
      { "name": "crm", "transport": "http", "url": "https://mcp.acme.com/crm", "tiers": ["ceo"] }
    ]
  },

  "escalation": {
    "require_user_consent": true,
    "max_attempts_per_tier": 3,
    "human_admin": {
      "email": "support-lead@acme.com",
      "push_topic": "acme-escalations",
      "scheduling_link": "https://cal.acme.com/acme-support"
    }
  }
}
```

**Personas are fully dynamic.** Companies set their real CEO's name — Jensen Huang, Tim Cook, Sam Altman, their own founder — while the rest of the chain keeps distinct personalities. The orchestrator reads names from config; nothing is hardcoded.

**Knowledge is drop-in.** Point at a domain, a public site, or a folder of PDFs and Markdown handbooks. The ingestion pipeline crawls, chunks, embeds, and indexes into Qdrant on first boot.

---

## Security model

Local MCP servers are arbitrary code from third parties. They're treated that way.

**Binary allowlist.** Stdio transport may only execute from a fixed set: `uvx`, `npx`, `docker`. Any other command in `company_config.json` is rejected at parse time, before a process is spawned.

**Container isolation.** Local MCP servers and all sandboxed code execution run in Docker containers with:
- No host filesystem mounts beyond an explicit, read-only allowlist
- Network egress restricted to declared endpoints
- CPU, memory, and wall-clock limits
- Non-root user, dropped capabilities, read-only root filesystem

**Capability by tier.** Tool bindings are injected per tier at startup. The Front Desk agent has no tool registry to call into — not a filtered one, an empty one. There is no prompt that talks it into a tool call.

**Guardrails on both ends.** Input guardrails at the Front Desk (injection, PII, abuse, scope); output guardrails at the CEO (hallucinated commitments, internal leakage, unsafe advice).

**Redaction at handoff.** PII is stripped once, at the tier boundary, and never re-enters an upstream prompt.

---

## Project structure

```
chain-of-command/
├── backend/
│   ├── graph/
│   │   ├── supervisor.py          # tier routing, escalation decisions
│   │   ├── tiers/
│   │   │   ├── front_desk.py      # no tools; guardrails + triage
│   │   │   ├── manager.py         # local tools, RAG, sandbox
│   │   │   ├── vice_president.py  # + external MCP, async tool loops
│   │   │   └── ceo.py             # + evaluator-optimizer, HITL
│   │   ├── handoff.py             # state summarization protocol
│   │   └── middleware/
│   │       ├── hitl.py            # conditional interrupts
│   │       └── guardrails.py
│   ├── mcp/
│   │   ├── internal_server.py     # first-party MCP tools
│   │   ├── registry.py            # config → tier tool injection
│   │   └── sandbox.py             # allowlist + Docker isolation
│   ├── rag/
│   │   ├── ingest.py              # PDFs, Markdown, crawl → Qdrant
│   │   └── retriever.py
│   ├── notifications/             # email · push · scheduling
│   ├── config/
│   │   ├── schema.py              # company_config.json validation
│   │   └── loader.py
│   └── api/                       # FastAPI + WebSocket streaming
├── frontend/
│   └── src/
│       ├── components/Chat/
│       ├── themes/                # per-tier visual identity
│       └── hooks/useEscalation.ts # tier transition animations
├── company_config.json
├── docker-compose.yml
└── README.md
```

---

## Getting started

> **Status:** early development. Steps below describe the intended setup.

**Prerequisites:** Docker & Docker Compose · Python 3.11+ · Node 20+ · [Ollama](https://ollama.com)

```bash
git clone <repo-url> && cd chain-of-command

# 1. Pull the models named in company_config.json
ollama pull llama3.2:3b
ollama pull qwen2.5:14b

# 2. Start Qdrant, the internal MCP server, and sandbox infrastructure
docker compose up -d

# 3. Configure your company
cp company_config.example.json company_config.json
$EDITOR company_config.json

# 4. Ingest knowledge sources into Qdrant
python -m backend.rag.ingest --config company_config.json

# 5. Run
uvicorn backend.api.main:app --reload      # backend  :8000
cd frontend && npm install && npm run dev  # frontend :5173
```

---

## Roadmap

- [ ] LangGraph tier subgraphs + supervisor routing
- [ ] Handoff packet schema and summarizer
- [ ] HITL interrupt middleware with checkpoint/resume
- [ ] Internal MCP server
- [ ] External MCP loader with binary allowlist + Docker sandboxing
- [ ] Qdrant ingestion (PDF, Markdown, web crawl)
- [ ] React frontend with per-tier theming and escalation transitions
- [ ] CEO evaluator–optimizer loop
- [ ] Email / push / call-scheduling integrations
- [ ] Tracing across tier boundaries
- [ ] Input and output guardrails
- [ ] `company_config.json` schema validation and hot reload
- [ ] Escalation-rate and resolution-per-tier analytics
