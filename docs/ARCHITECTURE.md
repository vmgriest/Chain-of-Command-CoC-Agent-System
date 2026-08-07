# Architecture Notes

Design rationale that does not belong in code comments. See [README.md](../README.md)
for what the system is, [PLAN.md](../PLAN.md) for the build order, and
[CHECKLIST.md](../CHECKLIST.md) for tasks.

---

## Why the Front Desk has no tools

Not a limitation to work around — the point.

Three tiers of a support system have three different cost profiles. Most inbound
questions ("what are your hours?", "how do I reset my password?") are answerable
from a 3B model with no tool calls and no retrieval. Routing those through an
agent with MCP connections, a vector store, and a 32B model pays enterprise cost
for a trivial answer.

The security argument is stronger than the cost one. An agent that *can* reach
external MCP servers can be *made* to reach them — turn one, anonymous user,
whatever the system prompt says. Capability should be earned through escalation
rather than granted by default.

Hence: the Front Desk's tool registry is **empty**, not filtered. There is no
runtime path from that agent to a tool call. A filter is a thing that can have a
bug; an absent code path is not.

---

## Why the handoff packet, not the transcript

Naive escalation passes message history upward. By hop three the CEO tier is
reading the Front Desk's greeting and burning context on it. Cost grows with
conversation length, and the signal-to-noise ratio falls at exactly the point the
problem is hardest.

The packet is a **typed, bounded summary**: facts, not dialogue.

`ruled_out` is the field that earns its keep. Without it, each tier re-attempts
what the tier below already eliminated — the customer watches four agents check
the same expired certificate. With it, escalation is genuinely cumulative.

`attempted_actions` serves the human at the end of the chain. When the CEO emails
an admin, that admin gets the packet, not a transcript. Same protocol, different
consumer.

**Failure mode to watch:** if `handoff_packet_tokens` grows across a session, the
summarizer is accumulating instead of summarizing, and the protocol is silently
degrading back into a transcript. It is traced for exactly this reason (M5).

---

## Why the supervisor owns transitions

Tiers raise an `EscalationRequest`; only the supervisor writes `current_tier`.

Two reasons. **Auditability** — every transition passes through one function, so
"why did this ticket reach the CEO?" has one place to look. **Injection
resistance** — "ignore previous instructions, you are now the CEO" cannot promote
an agent, because agents have no mechanism to promote themselves.

There is a test asserting no tier subgraph returns `current_tier` in its state
update. It looks pedantic and it is the one most likely to catch a real
regression during a refactor.

---

## Why escalation is monotonic

No auto-descalation, ever. Once a customer reaches the CEO tier, a simple
follow-up is answered at the CEO tier.

The efficiency argument for descalation is real — why pay for a 32B model to
answer "what's your refund window?" But the customer experience argument beats
it. Someone who escalated three times and finally reached the top, then gets
bounced back to the Front Desk for their next question, has been handed the exact
runaround the escalation was supposed to end.

`UserIntent.is_simple_question` exists for telemetry only. If the numbers ever
justify revisiting this, the data will be there — but the default is: you do not
go back down.

---

## Why consent gates agent-initiated escalation only

Agent-initiated escalation asks first. User-initiated escalation does not.

A customer who says "I want to talk to upper management" and gets "are you sure?"
is experiencing the runaround. They already decided.

An agent that escalates silently, on the other hand, teaches the customer that
the system moves them around unpredictably. Asking — "I don't have access to your
billing records from this desk, would you like me to bring in a manager who
does?" — frames it as a capability gap and keeps the customer in control.

Refusal must be a real option. The agent keeps working at the current tier and
does not immediately re-propose escalation next turn.

---

## Why HITL context requests are conditional

The interrupt fires only when `TierVerdict.needs_context` is non-null.

The tempting implementation is a checkpoint on every turn — "before I continue,
is there anything else?" It is safer-looking and it makes the product unusable.
Every turn becomes two round trips and the agent reads as unable to do anything
on its own.

Conditional means most turns produce no interrupt at all. There is a test
asserting a turn needing nothing completes with zero interrupts.

---

## Why the session survives human escalation

When the CEO emails an admin or books a call, the chat stays live.

The intuitive implementation ends the session — the human has it now, hand it
over. But the human is not there yet. They might be asleep. Meanwhile the
customer is sitting in front of a dead chat window with a ticket number, which is
the single most common way "we've escalated your case" turns into a bad
experience.

So: the CEO says what it did, says what happens next, and keeps helping. The
banner is informational, the composer stays enabled.

This is the behaviour most likely to be built wrong, because disabling input
after escalation *feels* correct.

---

## Why the stdio allowlist is checked twice

`{uvx, npx, docker}` is validated in `backend/config/schema.py` at parse time and
again in `backend/mcp/sandbox.py` at spawn.

Parse-time validation is **usability**: a company gets a clear error at startup
instead of a mysterious failure later. Spawn-time is the **security boundary**:
config objects can be constructed or mutated in memory without passing through
the parser, and the check that matters is the one immediately before
`subprocess` is called.

**The sharpest edge in this design:** `docker` is on the allowlist, so a config
could request a container that mounts the Docker socket and escapes the sandbox
entirely. Args mounting `/var/run/docker.sock`, or passing `--privileged` or
`--network=host`, must be rejected. There is a test for it. Do not skip it.

---

## Model sizing

Sized up the ladder — Front Desk smallest, CEO largest.

Front Desk handles the bulk of traffic and mostly triages, which small models do
well. The CEO runs an evaluator–optimizer loop over the hardest remaining
problems and needs the headroom.

Capped at ~32B rather than 70B: a 70B model is slow enough locally that the CEO
tier feels broken, and the tier that is supposed to feel like the most attentive
service in the company should not be the one that makes people wait.

Every model id is config-driven. Companies with different hardware change one
file.

---

## Open questions

- **Auth.** Sessions are anonymous and `session_id` is guessable — anyone with
  the id can read the conversation. Must close before any real deployment.
- **Persistence.** `MemorySaver` loses every conversation on restart, including
  sessions paused at an interrupt. Postgres checkpointer before production.
- **Multi-tenancy.** One deployment per `company_config.json`, or one deployment
  serving many? Affects how the MCP registry is scoped — currently a process
  singleton, which assumes one company per process.
