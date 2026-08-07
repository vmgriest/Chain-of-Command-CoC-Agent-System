/**
 * Root chat shell. Owns the theme wrapper and lays out header / messages /
 * input / pending prompts.
 */

// TODO(M1): ChatContainer
//
//   Layout:
//     <div ref={themeRoot}>            <- CSS custom properties applied here
//       <AgentHeader />                <- current persona + tier badge
//       <MessageList />                <- scrollback, incl. TierTransition markers
//       {pendingEscalation && <EscalationPrompt />}
//       {pendingContext    && <ContextRequest />}
//       {humanEscalated    && <HumanEscalationBanner />}
//       <MessageInput />               <- disabled while transitioning or pending
//     </div>
//
// TODO(M1): applyTheme() into themeRoot whenever the tier changes.
//
// TODO(M1): at most ONE pending prompt renders at a time. Two open prompts means
//   the UI and the paused graph have diverged.
//
// TODO(M4): the human-escalation banner is sticky and the chat stays fully
//   usable underneath it. This is the behaviour most likely to get built wrong —
//   the intuitive move is to disable input once a human is involved, and that is
//   exactly what must NOT happen.

export function ChatContainer(): JSX.Element {
  throw new Error('not implemented');
}
