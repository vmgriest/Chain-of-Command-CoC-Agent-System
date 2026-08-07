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

export type ServerEvent =
  | TokenEvent
  | AgentIntroEvent
  | TierChangeEvent
  | EscalationPromptEvent
  | ContextRequestEvent
  | HumanEscalationEvent
  | ErrorEvent;

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
