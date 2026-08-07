/**
 * App root.
 */

// TODO(M1): App
//   1. Resolve sessionId from localStorage, or mint a new one
//   2. fetchConfig() on mount — persona names and themes come from the server,
//      never hardcoded here
//   3. Render <ChatContainer /> once config has loaded
//   4. Loading and error states while config is in flight
//
// TODO(M1): error boundary around ChatContainer. A render crash mid-conversation
//   should offer a reload that RECONNECTS to the same session rather than
//   discarding it — the server-side checkpoint still has the conversation.

export function App(): JSX.Element {
  throw new Error('not implemented');
}

export default App;
