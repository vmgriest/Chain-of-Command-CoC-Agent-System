/**
 * App root.
 */

import { Component, type ReactNode, useEffect, useState } from 'react';
import { MotionConfig } from 'framer-motion';

import { ChatContainer } from '@/components/Chat/ChatContainer';
import { fetchConfig } from '@/lib/api';
import { useChatStore } from '@/store/chat';

/** A render crash mid-conversation offers a reload that RECONNECTS to the same
 *  session (sessionId lives in localStorage) rather than discarding it — the
 *  server-side checkpoint still has the conversation. */
class ChatErrorBoundary extends Component<{ children: ReactNode }, { crashed: boolean }> {
  state = { crashed: false };

  static getDerivedStateFromError(): { crashed: boolean } {
    return { crashed: true };
  }

  render(): ReactNode {
    if (this.state.crashed) {
      return (
        <div className="flex h-screen flex-col items-center justify-center gap-3 text-center">
          <p>Something went wrong displaying the conversation.</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-lg border px-4 py-2 text-sm font-medium"
          >
            Reload and reconnect
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function App(): JSX.Element {
  const setConfig = useChatStore((s) => s.setConfig);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');

  useEffect(() => {
    let cancelled = false;
    fetchConfig()
      .then((config) => {
        if (cancelled) return;
        // Persona names and themes come from the server, never hardcoded here.
        setConfig(config);
        setStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [setConfig]);

  if (status === 'loading') {
    return (
      <div className="flex h-screen items-center justify-center text-slate-500">
        Loading…
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 text-center">
        <p>Couldn't reach the support service.</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-lg border px-4 py-2 text-sm font-medium"
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <MotionConfig reducedMotion="user">
      <ChatErrorBoundary>
        <ChatContainer />
      </ChatErrorBoundary>
    </MotionConfig>
  );
}

export default App;
