/**
 * WebSocket wire protocol.
 *
 * ⚠ Mirrors backend/api/events.py. Change both or neither.
 *
 * Tier transitions arrive as EXPLICIT events. The UI never infers a handoff from
 * message content — sniffing a token stream for "Hi, I'm Dwight" would be
 * fragile and untestable.
 */

export type Tier = 'front_desk' | 'manager' | 'vice_president' | 'ceo';

export const TIER_ORDER: Tier[] = ['front_desk', 'manager', 'vice_president', 'ceo'];

// --- server -> client ------------------------------------------------------

export interface TokenEvent {
  type: 'token';
  content: string;
}

export interface AgentIntroEvent {
  type: 'agent_intro';
  tier: Tier;
  persona_name: string;
  persona_title: string;
}

export interface TierChangeEvent {
  type: 'tier_change';
  from_tier: Tier;
  to_tier: Tier;
  from_persona: string;
  to_persona: string;
  theme: string;
  reason: string;
  /** Short line rendered in the transition divider, e.g. "Carrying over:
   *  account #48812, Okta IdP, cert issues ruled out". Makes the handoff
   *  protocol visible to the customer rather than implicit. */
  packet_summary: string;
}

export interface EscalationPromptEvent {
  type: 'escalation_prompt';
  from_tier: Tier;
  to_tier: Tier;
  to_persona: string;
  to_title: string;
  reason: string;
  question: string;
}

export interface ContextRequestEvent {
  type: 'context_request';
  question: string;
  persona_name: string;
}

export interface HumanEscalationEvent {
  type: 'human_escalation';
  channels: string[];
  scheduling_link: string | null;
  message: string;
  /** Always true. The chat does NOT end when a human is looped in. */
  session_continues: boolean;
}

export interface ErrorEvent {
  type: 'error';
  message: string;
  recoverable: boolean;
}

/** The current turn's streaming is done — whether it ended normally or paused
 *  at an interrupt. The client cannot tell "no tokens yet" from "no tokens
 *  ever" without this, so it's explicit rather than inferred. */
export interface TurnEndEvent {
  type: 'turn_end';
}

// A "discriminated union": every member has a `type` field with a distinct
// literal value. TypeScript narrows automatically from a `switch (event.type)`
// or `if (event.type === 'token')` — no separate tagged-union helper needed,
// unlike the Pydantic side (backend/api/events.py), which does need one to
// validate raw JSON into the right model.
export type ServerEvent =
  | TokenEvent
  | AgentIntroEvent
  | TierChangeEvent
  | EscalationPromptEvent
  | ContextRequestEvent
  | HumanEscalationEvent
  | ErrorEvent
  | TurnEndEvent;

// --- client -> server ------------------------------------------------------

export interface UserMessage {
  type: 'user_message';
  content: string;
}

export interface EscalationResponse {
  type: 'escalation_response';
  approved: boolean;
}

export interface ContextResponse {
  type: 'context_response';
  answer: string;
}

export type ClientEvent = UserMessage | EscalationResponse | ContextResponse;

// --- view models -----------------------------------------------------------

export interface ChatMessage {
  id: string;
  kind: 'message';
  role: 'user' | 'agent';
  content: string;
  /** Which tier said it — messages keep their original tier styling after an
   *  escalation, so the conversation reads as a visible history of the handoffs. */
  tier: Tier;
  personaName?: string;
  streaming?: boolean;
}

export interface PersonaInfo {
  name: string;
  title: string;
  theme: string;
}

/** From GET /api/config. Public — contains no MCP commands or admin contacts. */
export interface PublicConfig {
  company_name: string;
  personas: Record<Tier, PersonaInfo>;
}
